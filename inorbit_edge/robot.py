#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
from inorbit_edge import __version__ as inorbit_edge_version
import os
import logging
import paho.mqtt.client as mqtt
from urllib.parse import urlsplit
import socks
import ssl
import threading
from inorbit_edge.inorbit_pb2 import (
    CustomDataMessage,
    KeyValueCustomElement,
    LocationAndPoseMessage,
    OdometryDataMessage,
    LaserMessage,
    PathPoint,
    RobotPath,
    PathDataMessage,
    Echo,
    CustomScriptCommandMessage,
    CustomScriptStatusMessage,
    CameraMessage,
)
from inorbit_edge.video import CameraStreamer, Camera
import time
import requests
import math
from inorbit_edge.utils import encode_floating_point_list
import certifi
import subprocess
import re
from deprecated import deprecated

INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL = "https://control.inorbit.ai/cloud_sdk_robot_config"

MQTT_SUBTOPIC_POSE = "ros/loc/data2"
MQTT_SUBTOPIC_PATH = "ros/loc/path"
MQTT_SUBTOPIC_LASER_CONFIG = "ros/loc/config/0"
MQTT_SUBTOPIC_ODOMETRY = "ros/odometry/data"
MQTT_SUBTOPIC_CUSTOM_DATA = "custom"
MQTT_SUBTOPIC_CUSTOM_COMMAND = "custom_command"
MQTT_SUBTOPIC_STATE = "state"
MQTT_SUBTOPIC_CAMERA_V2 = "ros/camera2"
MQTT_SUBTOPIC_OUT_CMD = "out_cmd"

MQTT_TOPIC_ECHO = "echo"
MQTT_NAV_GOAL_GOAL = "ros/loc/nav_goal"
MQTT_NAV_GOAL_MULTI = "ros/loc/goal_path"
MQTT_INITIAL_POSE = "ros/loc/set_pose"
MQTT_CUSTOM_COMMAND = "custom_command/script/command"
MQTT_SCRIPT_OUTPUT_TOPIC = "custom_command/script/status"
MQTT_IN_CMD = "in_cmd"

# InOrbit commands
COMMAND_INITIAL_POSE = "initialPose"
COMMAND_NAV_GOAL = "navGoal"
COMMAND_CUSTOM_COMMAND = "customCommand"
# InOrbit modules
INORBIT_MODULE_CAMERAS = "RosImageAgentlet"
# CustomCommand execution status
CUSTOM_COMMAND_STATUS_FINISHED = "finished"
CUSTOM_COMMAND_STATUS_ABORTED = "aborted"

ROBOT_PATH_POINTS_LIMIT = 1000


class RobotSession:
    def __init__(self, robot_id, robot_name, api_key, **kwargs) -> None:
        """Initialize a robot session.

        Args:
            robot_id (str): ID of the robot.
            robot_name (str): Robot name.
            api_key (str): API key for authenticating against InOrbit Cloud services.
            endpoint (str): InOrbit URL. Defaults: INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL.
            use_ssl (bool): Configures MQTT client to use SSL. Defaults: True.
        """

        self.logger = logging.getLogger(__class__.__name__)

        self.robot_id = robot_id
        self.robot_name = robot_name
        self.api_key = api_key
        # The agent version is generated based on the InOrbit Edge SDK version
        self.agent_version = "{}.edgesdk_py".format(inorbit_edge_version)
        self.endpoint = kwargs.get("endpoint", INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL)

        # Use SSL by default
        self.use_ssl = kwargs.get("use_ssl", True)

        # Use TCP transport by default. The client will use websockets
        # transport if the environment variable HTTP_PROXY is set.
        self.use_websockets = kwargs.get("use_websockets", False)

        # Read optional proxy configuration from environment variables
        # We use ``self.http_proxy`` to indicate if proxy configuration should be used.
        # TODO: enable explicit proxy configuration on ``RobotSession`` constructor.
        self.http_proxy = os.getenv("HTTP_PROXY")
        if self.http_proxy == "":
            self.logger.warn("Found empty HTTP_PROXY variable. Ignoring.")
            self.http_proxy = None
        if self.http_proxy is not None:
            self.logger.info(
                "Found HTTP_PROXY environment configuration = {:}. "
                "Will use WebSockets transport.".format(self.http_proxy)
            )
            self.use_websockets = True

        # Create mqtt client
        if self.use_websockets:
            self.client = mqtt.Client(protocol=mqtt.MQTTv311, transport="websockets")
            self.logger.debug("MQTT client created using websockets transport")
        else:
            self.client = mqtt.Client(protocol=mqtt.MQTTv311, transport="tcp")
            self.logger.debug("MQTT client created using tcp transport")

        # Configure proxy hostname and port if necessary
        if self.http_proxy is not None:
            parts = urlsplit(self.http_proxy)
            proxy_hostname = parts.hostname
            proxy_port = parts.port

            if not proxy_port:
                self.logger.warn("Empty proxy port. Is 'HTTP_PROXY' correct?")

            self.logger.debug(
                "Configuring client proxy: {}:{}".format(proxy_hostname, proxy_port)
            )
            self.client.proxy_set(
                proxy_type=socks.HTTP, proxy_addr=proxy_hostname, proxy_port=proxy_port
            )

        # Register MQTT client callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        # Functions to handle incoming MQTT messages.
        # They are mapped by MQTT subtopic e.g.
        # 'ros/loc/set_pose': set_pose_message_handler
        self.message_handlers = {}

        self.command_callbacks = []
        self.camera_streamers = {}
        self.camera_streaming_on = False
        self.camera_streaming_mutex = threading.Lock()
        self.message_handlers[MQTT_INITIAL_POSE] = self._handle_initial_pose
        self.message_handlers[MQTT_CUSTOM_COMMAND] = self._handle_custom_command
        self.message_handlers[MQTT_NAV_GOAL_GOAL] = self._handle_nav_goal
        self.message_handlers[MQTT_IN_CMD] = self._handle_in_cmd

        # Internal variables for configuring throttling
        # The throttling is done by method instead of by topic because the same topic
        # might be used for sending different type of messages e.g. pose and laser.
        # Each throttling has a ``last_ts`` that is the last time a method was called
        # and a ``min_time_between_calls`` to configure what is the min time to wait
        # before method calls.
        self._publish_throttling = {
            "publish_pose": {
                "last_ts": 0,
                "min_time_between_calls": 1,  # seconds
            },
            "publish_key_values": {
                "last_ts": 0,
                "min_time_between_calls": 1,  # seconds
            },
            "publish_odometry": {
                "last_ts": 0,
                "min_time_between_calls": 1,  # seconds
            },
            "publish_laser": {
                "last_ts": 0,
                "min_time_between_calls": 1,  # seconds
            },
            "publish_path": {
                "last_ts": 0,
                "min_time_between_calls": 1,  # seconds
            },
        }

    def _get_robot_subtopic(self, subtopic):
        """Build topic for this robot.

        It returns a robot topic by concatenating the robot id
        base topic with the provided subtopic.

        Args:
            subtopic (str): robot subtopic.

        Returns:
            str: robot topic.
        """
        if subtopic.startswith("/"):
            raise ValueError("Subtopic shouldn't start with '/'.")

        return "r/{robot_id}/{subtopic}".format(
            robot_id=self.robot_id, subtopic=subtopic
        )

    def _should_publish_message(self, method):
        """Determine if the method should be executed or not

        It uses robot session property ``self._publish_throttling`` to
        determine if the method has not been called before the configured
        time. If the method can be called, it also updates the method last
        call timestamp.

        Args:
            method (str): method name.

        Returns:
            bool: True if the method can be called.
        """
        try:
            throttling_cfg = self._publish_throttling[method]
        except KeyError:
            self.logger.error(
                "Trying to publish using a method with no throttling configured."
            )
            raise

        current_ts = time.time()
        time_diff = current_ts - throttling_cfg["last_ts"]
        if time_diff < throttling_cfg["min_time_between_calls"]:
            self.logger.debug(
                (
                    "Ignoring message '{}' (robot '{}'). Last "
                    "message was sent {:.4f} seconds ago."
                ).format(method, self.robot_id, time_diff)
            )
            return False

        throttling_cfg["last_ts"] = current_ts
        return True

    def _fetch_robot_config(self):
        """Gets robot config by posting appkey and robot/agent info.
        All params are provided on the RobotSession constructor
        """
        self.logger.info("Fetching config for robot {}".format(self.robot_id))
        # get params from self
        params = {
            "appKey": self.api_key,
            "robotId": self.robot_id,
            "hostname": self.robot_name,
            "agentVersion": self.agent_version,
        }

        # post request to fetch robot config
        response = requests.post(self.endpoint, data=params)
        response.raise_for_status()

        # TODO: validate fetched config
        return response.json()

    def _on_connect(self, client, userdata, flags, rc):
        """MQTT client connect callback.

        Args:
            client:     the client instance for this callback
            userdata:   the private user data as set in Client() or userdata_set()
            flags:      response flags sent by the broker
            rc:         the connection result
        """

        # Only assume that the robot is connected if return code is 0.
        # Other values are taken as errors (check here:
        # http://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html#_Toc398718035)
        # so connection process needs to be aborted.
        if rc == 0:
            self.logger.info("Connected to MQTT")
        else:
            self.logger.warn("Unable to connect. rc = {:d}.".format(rc))
            return

        # Send robot online status.
        # This method is blocking so do it on a separate thread just in case.
        threading.Thread(
            target=self._send_robot_status, kwargs={"robot_status": "1"}
        ).start()

        # Subscribe to interesting topics
        self.client.subscribe(
            topic=self._get_robot_subtopic(subtopic=MQTT_INITIAL_POSE)
        )
        self.client.subscribe(
            topic=self._get_robot_subtopic(subtopic=MQTT_CUSTOM_COMMAND)
        )
        self.client.subscribe(
            topic=self._get_robot_subtopic(subtopic=MQTT_NAV_GOAL_GOAL)
        )
        self.client.subscribe(topic=self._get_robot_subtopic(subtopic=MQTT_IN_CMD))
        # ask server to resend modules, so our state is consistent with the server side
        self._resend_modules()

    def _on_message(self, client, userdata, msg):
        """MQTT client message callback.

        Args:
            client:     the client instance for this callback
            userdata:   the private user data as set in Client() or userdata_set()
            msg:        an instance of MQTTMessage. This is a class with
                        members topic, payload, qos, retain.
        """

        try:
            self._send_echo(msg.topic, msg.payload)
            subtopic = "/".join(msg.topic.split("/")[2:])
            if subtopic in self.message_handlers:
                self.message_handlers[subtopic](msg.payload)
        except UnicodeDecodeError as ex:
            self.logger.error(
                f"Failed to decode message, ignoring. Payload: '{msg.payload}'. {ex}"
            )
        except Exception:
            # Re-raise any other error
            self.logger.error("Unexpected error while processing message.")
            raise

    def _on_disconnect(self, client, userdata, rc):
        """MQTT client disconnect callback.

        Args:
            client:     the client instance for this callback
            userdata:   the private user data as set in Client() or userdata_set()
            rc:         disconnection result
        """

        if rc != 0:
            self.logger.warn(
                "Unexpected disconnection: {}".format(mqtt.error_string(rc))
            )
        else:
            self.logger.info("Disconnected from MQTT broker")

    def _send_echo(self, topic, payload):
        """Sends an echo response to the server.

        Args:
            topic: topic in which the message has been published
            payload: message payload
        """
        msg = Echo()
        msg.topic = topic
        msg.time_stamp = int(time.time() * 1000)
        msg.string_payload = payload.decode("utf-8", errors="ignore")
        self.publish_protobuf(subtopic=MQTT_TOPIC_ECHO, message=msg)

    def _handle_initial_pose(self, msg):
        """Handle incoming MQTT_INITIAL_POSE message."""

        args = msg.decode("utf-8").split("|")
        seq = args[0]
        ts = args[1]  # noqa: F841
        x = args[2]
        y = args[3]
        theta = args[4]

        # Hand over to callback for processing, using the proper format
        self._dispatch_command(
            command_name=COMMAND_INITIAL_POSE,
            args=[{"x": x, "y": y, "theta": theta}],
            execution_id=seq,  # NOTE: Using seq as the execution ID
        )

    def _handle_custom_command(self, msg):
        """Handle incoming MQTT_CUSTOM_COMMAND message."""

        custom_script_msg = CustomScriptCommandMessage()
        custom_script_msg.ParseFromString(msg)
        # Hand over to callback for processing, using the proper format
        self._dispatch_command(
            command_name=COMMAND_CUSTOM_COMMAND,
            args=[custom_script_msg.file_name, custom_script_msg.arg_options],
            execution_id=custom_script_msg.execution_id,
        )

    def _handle_nav_goal(self, msg):
        """Handle incoming MQTT_NAV_GOAL_GOAL message."""

        args = msg.decode("utf-8").split("|")
        seq = args[0]
        ts = args[1]  # noqa: F841
        x = args[2]
        y = args[3]
        theta = args[4]
        # Hand over to callback for processing, using the proper format
        self._dispatch_command(
            command_name=COMMAND_NAV_GOAL,
            args=[{"x": x, "y": y, "theta": theta}],
            execution_id=seq,  # NOTE: Using seq as the execution ID
        )

    def _handle_in_cmd(self, msg):
        """Handles an in_cmd message"""
        args = msg.decode("utf-8").split("|")
        if len(args) < 1:
            return
        if args[0] == "load_module" and len(args) >= 3:
            self._handle_load_module(args[1], args[2])
        if args[0] == "unload_module" and len(args) >= 2:
            self._handle_unload_module(args[1])

    def _handle_load_module(self, module_name, run_level):
        """Handles a load_module command"""
        if module_name == INORBIT_MODULE_CAMERAS:
            self._start_cameras_streaming()

    def _handle_unload_module(self, module_name):
        """Handles an unload_module command"""
        if module_name == INORBIT_MODULE_CAMERAS:
            self._stop_cameras_streaming()

    def _start_cameras_streaming(self):
        """Start streaming on all registered cameras"""
        with self.camera_streaming_mutex:
            self.camera_streaming_on = True
            for s in self.camera_streamers.values():
                s.start()

    def _stop_cameras_streaming(self):
        """Start streaming on all registered cameras"""
        with self.camera_streaming_mutex:
            self.camera_streaming_on = False
            for s in self.camera_streamers.values():
                s.stop()

    def publish_camera_frame(self, camera_id, image, width, height, ts):
        """Publishes a camera frame"""
        msg = CameraMessage()
        msg.camera_id = camera_id
        msg.width = width
        msg.height = height
        msg.ts = ts
        msg.image = image
        self.publish_protobuf(MQTT_SUBTOPIC_CAMERA_V2, msg)

    def _dispatch_command(self, command_name, args, execution_id):
        """Executes registered command callbacks for a specific incoming command."""
        for callback in self.command_callbacks:

            def result_function(result_code):
                return self.report_command_result(args, execution_id, result_code)

            # TODO: Implement progress reporting function
            def progress_function(output, error):
                return 1

            options = {
                "result_function": result_function,
                "progress_function": progress_function,
                "metadata": {},
            }
            callback(command_name, args, options)

    def report_command_result(self, args, execution_id, result_code):
        """Send to server the result code of a command executed by a user callback."""

        msg = CustomScriptStatusMessage()
        msg.file_name = args[0]
        msg.execution_id = execution_id
        msg.execution_status = (
            CUSTOM_COMMAND_STATUS_FINISHED
            if result_code == "0"
            else CUSTOM_COMMAND_STATUS_ABORTED
        )
        msg.return_code = result_code
        self.publish_protobuf(MQTT_SCRIPT_OUTPUT_TOPIC, msg)

    def register_commands_path(self, path="./user_scripts", exec_name_regex=r".*"):
        """Registers executable commands that handle InOrbit custom command actions.
        Use `exec_name_regex` and `path` to customize which executables can be
        accessed. Note that if an action script name matches `exec_name_regex`, then
        the program will be executed prepending the provided `path`.
        """

        def handler(command_name, args, options):
            if command_name != COMMAND_CUSTOM_COMMAND:
                return
            script_name = args[0]
            script_args = args[1]
            if re.match(exec_name_regex, script_name):
                # TODO(mike) handle script return and output
                try:
                    subprocess.Popen(
                        [f"{path}/{script_name}"] + list(script_args),
                        shell=False,
                        env=dict(os.environ, INORBIT_ROBOT_ID=self.robot_id),
                    )
                except Exception as ex:
                    self.logger.error(
                        f"Failed to run executable command: {script_name} {ex}"
                    )
                    options["result_function"]("1")

        self.register_command_callback(handler)

    def register_command_callback(self, callback):
        """Register a function to be called when a command for the robot is received.

        Args:
            callback (callable): callback method for messages. The callback signature
                is `callback(command_name, args, options)`:
                - `command_name` identifies the specific command to be executed.
                - `args` is an ordered list with each argument as an entry. Each
                  element of the array can be a string or an object, depending on
                  the definition of the action.
                - `options`: is a dictionary that includes:
                  - `result_function` can be called to report command execution result.
                    It has the following signature: `result_function(return_code)`.
                  - `progress_function` can be used to report command output and has
                    the following signature: `progress_function(output, error)`.
                  - `metadata` is reserved for the future and will contains additional
                    information about the received command request.
        """

        self.logger.info(
            "Registering callback '{}' for robot '{}'".format(
                callback.__name__, self.robot_id
            )
        )

        # Don't do anything if callback is not a valid function
        if not callable(callback):
            return

        self.command_callbacks.append(callback)

    def unregister_command_callback(self, callback):
        """Unregisters the specified callback"""
        # TODO: Implement
        pass

    def register_camera(self, camera_id: str, camera: Camera):
        """Registers a camera. Video will be automatically streamed from this camera
        when requested from the platform, for example when a user accesses the
        navigation view.
        """

        def publish(image, width, height, ts):
            self.publish_camera_frame(
                camera_id, image, int(width), int(height), int(ts)
            )

        self.camera_streamers[camera_id] = CameraStreamer(camera, publish)
        with self.camera_streaming_mutex:
            if self.camera_streaming_on:
                self.camera_streamers[camera_id].start()

    def _resend_modules(self):
        """Ask server to resend modules"""
        self.publish(
            self._get_robot_subtopic(subtopic=MQTT_SUBTOPIC_OUT_CMD),
            "resend_modules",
            qos=1,
        )

    def _send_robot_status(self, robot_status):
        """Sends robot online/offline status message.

        This method blocks until either the message
        is sent or the client errors out.

        Args:
            robot_status (Union[bool,str]): Connection status
                It supports ``bool`` and ``str`` values ("0" or "1")

        Raises:
            ValueError: on invalid ``robot_status``
        """

        # Validate ``robot_status`` parameter.
        if isinstance(robot_status, bool):
            robot_status = "1" if robot_status else "0"

        if robot_status not in ["0", "1"]:
            raise ValueError("Robot status must be boolean, '0' or '1'")

        # Every time we connect or disconnect to the service, send
        # updated status including online/offline bit
        status_message = "{}|{}|{}|{}".format(
            robot_status, self.robot_api_key, self.agent_version, self.robot_name
        )
        ret = self.publish(
            self._get_robot_subtopic(subtopic=MQTT_SUBTOPIC_STATE),
            status_message,
            qos=1,
            retain=True,
        )
        self.logger.info("Publishing status {}. ret = {}.".format(robot_status, ret))

        # TODO: handle errors while waiting for publish. Consider that
        # this method would typically run on a separate thread.
        ret.wait_for_publish()
        published = ret.is_published()

        self.logger.info(
            "Robot status '{}' published: {:b}.".format(robot_status, published)
        )

    def _is_connected(self):
        return self.client.is_connected()

    def _is_disconnected(self):
        return not self.client.is_connected()

    def _wait_for_connection_state(self, state_func):
        for _ in range(5):
            self.logger.info(
                "Waiting for MQTT connection state '{}' ...".format(state_func.__name__)
            )
            time.sleep(1)
            if state_func():
                return
        raise RuntimeError(
            "Connection state never reached: {}".format(state_func.__name__)
        )

    def connect(self):
        """Configures MQTT client and connect to the service."""
        try:
            robot_config = self._fetch_robot_config()
        except Exception:
            self.logger.error(
                "Failed to fetch config for robot {}".format(self.robot_id)
            )
            raise

        self.robot_api_key = robot_config["robotApiKey"]

        # Use username and password authentication
        self.client.username_pw_set(robot_config["username"], robot_config["password"])

        # Configure "will" message to ensure the robot state
        # is set to offline if connection is interrupted
        will_payload = "0|{}".format(self.robot_api_key)
        self.client.will_set(
            self._get_robot_subtopic(subtopic=MQTT_SUBTOPIC_STATE),
            will_payload,
            qos=1,
            retain=True,
        )

        # TODO: add support for user-provided CA certificate file.
        if self.use_ssl:
            self.logger.debug("Configuring client to use SSL")
            self.client.tls_set(certifi.where(), tls_version=ssl.PROTOCOL_TLSv1_2)

        # Configure MQTT client hostname and port
        hostname = robot_config["hostname"]
        port = (
            robot_config["websockets_port"]
            if self.use_websockets
            else robot_config["port"]
        )
        self.client.connect(hostname, port, keepalive=10)
        self.client.loop_start()
        self._wait_for_connection_state(self._is_connected)

        self.logger.info(
            "MQTT connection initiated. {}:{} ({})".format(
                hostname, port, "websockets" if self.use_websockets else "MQTT"
            )
        )

    def disconnect(self):
        """Ends session, disconnecting from cloud services"""
        self.logger.info("Ending robot session")
        self._send_robot_status(robot_status="0")

        # TODO: Unsubscribe from topics

        self.client.disconnect()

        self._wait_for_connection_state(self._is_disconnected)

    def publish(self, topic, message, qos=0, retain=False):
        """MQTT client wrapper method for publishing messages

        Args:
            topic (str): Topic where the message will be published.
            message (str): The actual message to send.
            qos (int, optional): The quality of service level to use. Defaults to 0.
            retain (bool, optional): If set to true, the message will be set as
                the "last known good"/retained message for the topic. Defaults to False.
        Returns:
            MQTTMessageInfo: Returns a MQTTMessageInfo class
        """
        try:
            info = self.client.publish(
                topic=topic, payload=message, qos=qos, retain=retain
            )
        except ValueError:
            self.logger.error("Payload greater than 268435455 bytes is not allowed")

        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            self.logger.warn(
                "There was a problem sending message {}: {}".format(
                    info.mid, mqtt.error_string(info.rc)
                )
            )

        return info

    def publish_protobuf(self, subtopic, message, qos=0, retain=False):
        """Publish protobuf messages to this robot session subtopic.

        The protobuf ``message`` is serialized and published to the robot ``subtopic``.

        Args:
            subtopic (str): Robot subtopic, without leading ``/``.
            message (protobuf.Message): Protobuf message.
            qos (int, optional): The quality of service level to use. Defaults to 0.
            retain (bool, optional): If set to true, the message will be set as
                the "last known good"/retained message for the topic. Defaults to False.
        """
        topic = self._get_robot_subtopic(subtopic=subtopic)
        self.logger.debug("Publishing to topic {}".format(topic))
        ret = self.publish(
            topic, bytearray(message.SerializeToString()), qos=qos, retain=retain
        )
        self.logger.debug("Return code: {}".format(ret))

    def publish_pose(self, x, y, yaw, frame_id="map", ts=None):
        """Publish robot pose

        Args:
            x (float): Robot pose x coordinate.
            y (float): Robot pose y coordinate.
            yaw (float): Robot yaw (radians).
            frame_id (str, optional): Robot map frame identifier. Defaults to "map".
            ts (int, optional): Pose timestamp. Defaults to int(time() * 1000).
        """
        if not self._should_publish_message(method="publish_pose"):
            return None

        msg = LocationAndPoseMessage()
        msg.ts = ts if ts else int(time.time() * 1000)
        msg.pos_x = x
        msg.pos_y = y
        msg.yaw = yaw
        msg.frame_id = frame_id
        self.publish_protobuf(MQTT_SUBTOPIC_POSE, msg)

    def publish_key_values(self, key_values, custom_field="0"):
        """Publish key value pairs

        Args:
            key_values (dict): Key value mappings to publish
            custom_field (str, optional): ID of the CustomData element. Defaults to "0".
        """

        if not self._should_publish_message(method="publish_key_values"):
            return None

        def convert_value(value):
            if isinstance(value, object):
                return json.dumps(value)
            else:
                return str(value)

        def set_pairs(key):
            item = KeyValueCustomElement()
            item.key = key
            item.value = convert_value(key_values[key])
            return item

        msg = CustomDataMessage()
        msg.custom_field = custom_field

        msg.key_value_payload.pairs.extend(map(set_pairs, key_values.keys()))

        self.publish_protobuf(MQTT_SUBTOPIC_CUSTOM_DATA, msg)

    def publish_odometry(
        self,
        ts_start=None,
        ts=None,
        linear_distance=0,
        angular_distance=0,
        linear_speed=0,
        angular_speed=0,
    ):
        """Publish odometry data

        Args:
            ts_start (int, optional): Timestamp (milliseconds) when the started to
                accumulate odometry. Defaults to int(time() * 1000).
            ts (int, optional): Timestamp (milliseconds) of the last time odometry
                accumulator was updated. Defaults to int(time() * 1000).
            linear_distance (int, optional): Accumulated displacement (meters).
                Defaults to 0.
            angular_distance (int, optional): Accumulated rotation (radians).
                Defaults to 0.
            linear_speed (int, optional): Linear speed (m/s). Defaults to 0.
            angular_speed (int, optional): Angular speed (rad/s). Defaults to 0.
        """

        if not self._should_publish_message(method="publish_odometry"):
            return None

        msg = OdometryDataMessage()
        msg.ts_start = ts_start if ts_start else int(time.time() * 1000)
        msg.ts = ts if ts else int(time.time() * 1000)
        msg.linear_distance = linear_distance
        msg.angular_distance = angular_distance
        msg.linear_speed = linear_speed
        msg.angular_speed = angular_speed
        msg.speed_available = True
        self.publish_protobuf(MQTT_SUBTOPIC_ODOMETRY, msg)

    def publish_laser(
        self, x, y, yaw, ranges, angle=(-math.pi, math.pi), frame_id="map", ts=None
    ):
        """Publish robot laser scan

        Args:
            x (float): Robot pose x coordinate.
            y (float): Robot pose y coordinate.
            yaw (float): Robot yaw (radians).
            ranges (List[float]): Laser scan range data. This list of ``float`` number
                may contain infinite values represented as ``math.pi``.
            angle (tuple, optional): Laser scan range angle (radians). This parameter
                defines the cone in which the laser points will be shown. For full 360
                degrees scans use (-math.pi, math.pi). Defaults to (-math.pi, math.pi).
            frame_id (str, optional): Robot map frame identifier. Defaults to "map".
            ts (int, optional): Pose timestamp. Defaults to int(time() * 1000).
        """

        if not self._should_publish_message(method="publish_laser"):
            return None

        pb_lasers_message = LaserMessage()
        pb_lasers_message.name = "0"

        # Encode ranges list using a compact representation
        runs, values = encode_floating_point_list(ranges)

        # Update LaserMessage message with encoded laser ranges
        pb_lasers_message.ranges.runs.extend(runs)
        pb_lasers_message.ranges.values.extend(values)

        # Populate LocationAndPoseMessage with current pose
        # and laser data, encoded as floating point list.
        msg = LocationAndPoseMessage()
        msg.ts = ts if ts else int(time.time() * 1000)
        msg.pos_x = x
        msg.pos_y = y
        msg.yaw = yaw
        msg.frame_id = frame_id
        msg.lasers.append(pb_lasers_message)

        # Publish laser configuration, based on provided and/or infered parameters.
        # Note: x, y & yaw should be used if there is a robot to laser transform.
        #   As this is not supported they are explicitely set to zero.
        self.publish(
            topic=self._get_robot_subtopic(MQTT_SUBTOPIC_LASER_CONFIG),
            message=(
                "{ts:d}|{x:.4g}|{y:.4g}|{yaw:.6g}|{angle_min:.6g}|{angle_max:.6g}|"
                "{range_min:.4g}|{range_max:.4g}|{n_points:d}"
            ).format(
                ts=int(time.time() * 1000),
                x=0,
                y=0,
                yaw=0,
                angle_min=angle[0],
                angle_max=angle[1],
                range_min=min(pb_lasers_message.ranges.values),
                range_max=max(pb_lasers_message.ranges.values),
                n_points=len(ranges),
            ),
            qos=1,
            retain=True,
        )

        self.publish_protobuf(MQTT_SUBTOPIC_POSE, msg)

    def publish_path(self, path_points, path_id="0", ts=None):
        """Publish robot path

        Send a list of points representing the path the robot
        is traversing. This method only sends the data to InOrbit
        for displaying purposes, meaning that the path provided
        here won't make the robot to move

        Args:
            path_points (List[Tuple[int. int]]): List of x, y points
                the robot would go through.
        """

        if not self._should_publish_message(method="publish_path"):
            return None

        if len(path_points) > ROBOT_PATH_POINTS_LIMIT:
            self.logger.warn(
                "Path has {} points. Only the first {} points will be used.".format(
                    len(path_points), ROBOT_PATH_POINTS_LIMIT
                )
            )

        # Generate ``PathPoint`` protobuf messages
        # from the list of path point tuples
        pb_path_points = [
            PathPoint(x=path_point[0], y=path_point[1])
            for path_point in path_points[:ROBOT_PATH_POINTS_LIMIT]
        ]

        # Generate a ``RobotPath`` protobuf message and
        # add the list of ``PathPoint`` created above
        pb_robot_path = RobotPath()
        pb_robot_path.ts = ts if ts else int(time.time() * 1000)
        pb_robot_path.path_id = path_id
        pb_robot_path.points.extend(pb_path_points)

        # Publish ``PathDataMessage``
        msg = PathDataMessage()
        msg.ts = ts if ts else int(time.time() * 1000)
        msg.paths.append(pb_robot_path)

        self.publish_protobuf(MQTT_SUBTOPIC_PATH, msg)


class RobotSessionFactory:
    """Builds RobotSession objects using provided"""

    def __init__(self, **robot_session_kw_args):
        """Configures this factory with the arguments to pass to the
        constructor of instances.
        """
        self.robot_session_kw_args = robot_session_kw_args
        self.command_callbacks = []
        self.commands_paths_rules = []

    def build(self, robot_id, robot_name):
        """Builds a RobotSession object using the provided id and name.
        It also passes the robot_session_kw_args set when creating the factory to the
        RobotSession constructor.
        """
        session = RobotSession(robot_id, robot_name, **self.robot_session_kw_args)

        def build_callback(callback):
            def c(*args):
                callback(robot_id, *args)

            return c

        for command_callback in self.command_callbacks:
            session.register_command_callback(build_callback(command_callback))

        for path, exec_name_regex in self.commands_paths_rules:
            session.register_commands_path(path, exec_name_regex)
        return session

    def register_command_callback(self, callback):
        """Register a command callback to be used on all robot sessions created
        by this factory"""
        if not callable(callback):
            # Don't do anything if callback is not a valid function
            return

        self.command_callbacks.append(callback)

    def register_commands_path(self, path="./user_scripts", exec_name_regex=r".*"):
        """Registers executable commands that handle InOrbit custom command actions.
        Use `exec_name_regex` and `path` to customize which executables can be
        accessed. Note that if an action script name matches `exec_name_regex`, then
        the program will be executed prepending the provided `path`.
        """
        self.commands_paths_rules.append((path, exec_name_regex))


class RobotSessionPool:
    """Pool of robot sessions that handles connections for many robots in an
    efficient way"""

    def __init__(self, robot_session_factory):
        """Creates the pool
        Args:
          - robot_session_factory: factory used to build individual RobotSession
          objects
        """
        self.robot_session_factory = robot_session_factory
        self.robot_sessions = {}
        self.getting_session_mutex = threading.Lock()

    def get_session(self, robot_id, robot_name=""):
        """Returns a connected RobotSession for the specified robot"""
        # mutex to avoid the case of asking for the same robot twice and
        # opening 2 connections
        self.getting_session_mutex.acquire()
        # The `get_session` method might be called multiple times. Only create
        # connection and register callbacks for new robot sessions.
        new_robot_session = not self.has_robot(robot_id)
        try:
            if new_robot_session:
                self.robot_sessions[robot_id] = self.robot_session_factory.build(
                    robot_id, robot_name
                )
                self.robot_sessions[robot_id].connect()
            return self.robot_sessions[robot_id]
        finally:
            self.getting_session_mutex.release()

    def tear_down(self):
        """Destroys all RobotSession in this pool"""
        for rs in self.robot_sessions.values():
            rs.disconnect()
        self.robot_sessions = {}

    def has_robot(self, robot_id):
        """Checks if a RobotSession for a specific robot exists in this pool"""
        return robot_id in self.robot_sessions

    def free_robot_session(self, robot_id):
        """Destroys a RobotSession in this pool"""
        if not self.has_robot(robot_id):
            return
        sess = self.get_session(robot_id)
        sess.disconnect()
        del self.robot_sessions[robot_id]

    @deprecated(
        version="1.7.2",
        reason="use RobotSessionFactory.register_command_callback() instead",
    )
    def register_command_callback(self, callback):
        """Registers a callback to be called when a command is received"""
        self.robot_session_factory.register_command_callback(callback)
