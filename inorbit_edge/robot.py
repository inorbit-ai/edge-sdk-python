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
)
from time import time
from time import sleep
import requests
import math
from inorbit_edge.utils import encode_floating_point_list

INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL = "https://control.inorbit.ai/cloud_sdk_robot_config"

MQTT_POSE_TOPIC = "ros/loc/data2"
MQTT_TOPIC_CUSTOM_DATA = "custom"
MQTT_TOPIC_ODOMETRY = "ros/odometry/data"
MQTT_TOPIC_PATH = "ros/loc/path"

ROBOT_PATH_POINTS_LIMIT = 1000


class RobotSession:
    def __init__(self, robot_id, robot_name, api_key, **kwargs) -> None:
        """Initialize a robot session.

        Args:
            robot_id (str): ID of the robot.
            robot_name (str): Robot name.
            api_key (str): API key for authenticating against InOrbit Cloud services.
            custom_command_callback (callable): callback method for messages published
                on ``custom_command`` topic.
            endpoint (str): InOrbit URL. Defaults: INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL.
            use_ssl (bool): Configures MQTT client to use SSL. Defaults: True.
        """

        self.logger = logging.getLogger(__class__.__name__)

        self.robot_id = robot_id
        self.robot_name = robot_name
        self.api_key = api_key
        # The agent version is generated based on the InOrbit Edge SDK version
        self.agent_version = f"{inorbit_edge_version}.edgesdk_py"
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

        self.custom_command_callback = kwargs.get("custom_command_callback")

        # Register MQTT client callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

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

        # Configure custom command callback if provided
        if self.custom_command_callback:
            self.register_custom_command_callback(self.custom_command_callback)

    def _on_message(self, client, userdata, msg):
        """MQTT client connect callback.

        Args:
            client:     the client instance for this callback
            userdata:   the private user data as set in Client() or userdata_set()
            msg:        an instance of MQTTMessage. This is a class with
                        members topic, payload, qos, retain.
        """

        # Parse message and execute custom command callback
        if self.custom_command_callback:
            # Check if the message is coming from the custom command topic
            # TODO(lean): generalize to support subscribing multiple topics.
            #   Now it only supports the custom command topic.
            if msg.topic != self._get_custom_command_topic():
                self.logger.warn(
                    "Ignoring message from unsupported topic: {}".format(msg.topic)
                )
                return

            try:
                parsed_msg = json.loads(msg.payload.decode("utf-8"))
                self.custom_command_callback(self, parsed_msg)
            except json.decoder.JSONDecodeError:
                self.logger.error(
                    "Failed to parse JSON message, ignoring. {}".format(msg.payload)
                )
            except UnicodeDecodeError:
                self.logger.error(
                    "Failed to decode message, ignoring. {}".format(msg.payload)
                )
            except Exception:
                # Re-raise any other error
                self.logger.error("Unexpected error while processing message.")
                raise

    def _get_custom_command_topic(self):
        return "r/{}/custom_command".format(self.robot_id)

    def register_custom_command_callback(self, func):
        """Register custom command callback method and subscribes to
        custom command topic.

        Args:
            func (callable): callback method for messages published
                on ``custom_command`` topic.
        """

        self.logger.info(
            "Registering callback '{}' for robot '{}'".format(
                func.__name__, self.robot_id
            )
        )
        topic = self._get_custom_command_topic()
        self.logger.debug("Subscribing to topic '{}'".format(topic))
        self.client.subscribe(topic=topic)

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
            "r/{}/state".format(self.robot_id), status_message, qos=1, retain=True
        )
        self.logger.info("Publishing status {}. ret = {}.".format(robot_status, ret))

        # TODO: handle errors while waiting for publish. Consider that
        # this method would tipically run on a separate thread.
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
            sleep(1)
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
        will_topic = "r/{}/state".format(self.robot_id)
        will_payload = "0|{}".format(self.robot_api_key)
        self.client.will_set(will_topic, will_payload, qos=1, retain=True)

        # TODO: add support for user-provided CA certificate file.
        if self.use_ssl:
            self.logger.debug("Configuring client to use SSL")
            self.client.tls_set(
                "/etc/ssl/certs/ca-certificates.crt", tls_version=ssl.PROTOCOL_TLSv1_2
            )

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

        if self.custom_command_callback:
            topic = self._get_custom_command_topic()
            self.logger.info("Unsubscribing from topic '{}'".format(topic))
            self.client.unsubscribe(topic=topic)

        self.client.disconnect()

        self._wait_for_connection_state(self._is_disconnected)

        self.logger.info("Disconnected from MQTT broker")

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
        return self.client.publish(topic=topic, payload=message, qos=qos, retain=retain)

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
        topic = "r/{}/{}".format(self.robot_id, subtopic)
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
        msg = LocationAndPoseMessage()
        msg.ts = ts if ts else int(time() * 1000)
        msg.pos_x = x
        msg.pos_y = y
        msg.yaw = yaw
        msg.frame_id = frame_id
        self.publish_protobuf(MQTT_POSE_TOPIC, msg)

    def publish_key_values(self, key_values, custom_field="0"):
        """Publish key value pairs

        Args:
            key_values (dict): Key value mappings to publish
            custom_field (str, optional): ID of the CustomData element. Defaults to "0".
        """

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

        self.publish_protobuf(MQTT_TOPIC_CUSTOM_DATA, msg)

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
        msg = OdometryDataMessage()
        msg.ts_start = ts_start if ts_start else int(time() * 1000)
        msg.ts = ts if ts else int(time() * 1000)
        msg.linear_distance = linear_distance
        msg.angular_distance = angular_distance
        msg.linear_speed = linear_speed
        msg.angular_speed = angular_speed
        msg.speed_available = True
        self.publish_protobuf(MQTT_TOPIC_ODOMETRY, msg)

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
        msg.ts = ts if ts else int(time() * 1000)
        msg.pos_x = x
        msg.pos_y = y
        msg.yaw = yaw
        msg.frame_id = frame_id
        msg.lasers.append(pb_lasers_message)

        # Publish laser configuration, based on provided and/or infered parameters.
        # Note: x, y & yaw should be used if there is a robot to laser transform.
        #   As this is not supported they are explicitely set to zero.
        self.publish(
            topic="r/{robot_id}/ros/loc/config/{config_id:d}".format(
                robot_id=self.robot_id, config_id=0
            ),
            message=(
                "{ts:d}|{x:.4g}|{y:.4g}|{yaw:.6g}|{angle_min:.6g}|{angle_max:.6g}|"
                "{range_min:.4g}|{range_max:.4g}|{n_points:d}"
            ).format(
                ts=int(time() * 1000),
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

        self.publish_protobuf(MQTT_POSE_TOPIC, msg)

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
        pb_robot_path.ts = ts if ts else int(time() * 1000)
        pb_robot_path.path_id = path_id
        pb_robot_path.points.extend(pb_path_points)

        # Publish ``PathDataMessage``
        msg = PathDataMessage()
        msg.ts = ts if ts else int(time() * 1000)
        msg.paths.append(pb_robot_path)

        self.publish_protobuf(MQTT_TOPIC_PATH, msg)


class RobotSessionFactory:
    """Builds RobotSession objects using provided"""

    def __init__(self, **robot_session_kw_args):
        """Configures this factory with the arguments to pass to the
        constructor of instances.
        """
        self.robot_session_kw_args = robot_session_kw_args

    def build(self, robot_id, robot_name):
        """Builds a RobotSession object using the provided id and name.
        It also passes the  robot_session_kw_args set when creating the factory to the
        RobotSession constructor.
        """
        return RobotSession(robot_id, robot_name, **self.robot_session_kw_args)


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
        self.getting_session_mutex.acquire()
        try:
            # mutext to avoid the case of asking for the same robot twice and
            # opening 2 connections
            if not self.has_robot(robot_id):
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
