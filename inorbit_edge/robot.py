#!/usr/bin/env python
# -*- coding: utf-8 -*-

from inorbit_edge import __version__ as inorbit_edge_version
import os
import logging
import paho.mqtt.client as mqtt
from urllib.parse import urlsplit
import socks
import ssl
import threading

INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL = "https://control.inorbit.ai/cloud_sdk_robot_config"


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
        raise NotImplementedError()

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

    def connect(self):
        """Configures MQTT client and connect to the service."""
        # TODO: call _fetch_robot_config. Assuming it returns a dict
        robot_config = {
            "hostname": "localdev.com",
            "port": 1883,
            "protocol": "mqtt://",
            "websocket_port": 9001,
            "websocket_protocol": "ws://",
            "username": "sezonoquku",
            "password": "hDVop5dtN7MXkkY7",
            "robotApiKey": "H_2QCEQz6pD7i7xF",
        }

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
        self.client.connect_async(hostname, port, keepalive=10)
        self.client.loop_start()

        self.logger.info(
            "MQTT connection initiated. {}:{} ({})".format(
                hostname, port, "websockets" if self.use_websockets else "MQTT"
            )
        )

    def disconnect(self):
        """Ends session, disconnecting from cloud services"""
        self.logger.info("Ending robot session")
        self.send_robot_status(robot_status="0")

    def publish(self, topic, message, qos=0, retain=False):
        return self.client.publish(topic=topic, payload=message, qos=qos, retain=retain)
