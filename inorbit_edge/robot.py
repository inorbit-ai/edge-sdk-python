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
)
from time import time
from time import sleep
import requests


INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL = "https://control.inorbit.ai/cloud_sdk_robot_config"

MQTT_POSE_TOPIC = "ros/loc/data2"
MQTT_TOPIC_CUSTOM_DATA = "custom"


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

        # Register callbacks
        self.client.on_connect = self.on_connect

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

    def on_connect(self, client, userdata, flags, rc):
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
            target=self.send_robot_status, kwargs={"robot_status": "1"}
        ).start()

    def send_robot_status(self, robot_status):
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
            robot_status, self.api_key, self.agent_version, self.robot_name
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

        # Use username and password authentication
        self.client.username_pw_set(robot_config["username"], robot_config["password"])

        # Configure "will" message to ensure the robot state
        # is set to offline if connection is interrupted
        will_topic = "r/{}/state".format(self.robot_id)
        will_payload = "0|{}".format(self.api_key)
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
        self.send_robot_status(robot_status="0")
        self.client.disconnect()

        self._wait_for_connection_state(self._is_disconnected)

        self.logger.info("Disconnected from MQTT broker")

    def publish(self, topic, message, qos=0, retain=False):
        return self.client.publish(topic=topic, payload=message, qos=qos, retain=retain)

    def publish_protobuf(self, subtopic, message, qos=0, retain=False):
        topic = "r/{}/{}".format(self.robot_id, subtopic)
        self.logger.debug("Publishing to topic {}".format(topic))
        ret = self.publish(
            topic, bytearray(message.SerializeToString()), qos=qos, retain=retain
        )
        self.logger.debug("Return code: {}".format(ret))

    def publish_pose(self, x, y, yaw, frame_id="map", ts=None):
        message = LocationAndPoseMessage()
        message.ts = ts if ts else int(time() * 1000)
        message.pos_x = x
        message.pos_y = y
        message.yaw = yaw
        message.frame_id = frame_id
        self.publish_protobuf(MQTT_POSE_TOPIC, message)

    def publish_key_values(self, key_values, custom_field="0"):
        self.logger.info(
            "Publishing custom data key-values for robot {}".format(self.robot_id)
        )

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
