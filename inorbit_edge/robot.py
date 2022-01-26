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

class RobotSession:
    def __init__(self, robot_id, robot_name, app_key, **kwargs) -> None:
        """Initialize a robot session.

        Args:
            robot_id (str): ID of the robot
            robot_name (str): Robot name
            agent_version (str): Agent Version
            app_key (str): Application key for authenticating against InOrbit
            endpoint ([type]): InOrbit URL
        """

        self.logger = logging.getLogger(__class__.__name__)

        self.robot_id = robot_id
        self.robot_name = robot_name
        self.app_key = app_key
        self.agent_version = f"{inorbit_edge_version}.edgesdk_py"
        self.endpoint = kwargs.get(
            "endpoint", "https://control.inorbit.ai/cloud_sdk_robot_config"
        )

        self.use_ssl = kwargs.get("use_ssl", True)

        self.use_websocket = False

        # Read optional proxy configuration from the environment
        # We use self.http_proxy == None to indicate if proxy configuration should be used
        self.http_proxy = os.getenv("HTTP_PROXY")
        if self.http_proxy == "":
            self.logger.warn("Found empty HTTP_PROXY variable. Ignoring.")
            self.http_proxy = None
        if self.http_proxy is not None:
            self.logger.info(
                "Found HTTP_PROXY environment configuration = {:}. "
                "Will use WebSockets transport.".format(self.http_proxy)
            )
            self.use_websocket = True

        # Create mqtt client
        if self.use_websocket:
            self.client = mqtt.Client(protocol=mqtt.MQTTv311, transport="websockets")
        else:
            self.client = mqtt.Client(protocol=mqtt.MQTTv311)

        # Configure proxy hostname and port if necessary
        if self.http_proxy is not None:
            parts = urlsplit(self.http_proxy)
            proxy_hostname = parts.hostname
            proxy_port = parts.port

            self.logger.debug("Configuring client proxy: {}:{}".format(proxy_hostname, proxy_port))
            self.client.proxy_set(
                proxy_type=socks.HTTP, proxy_addr=proxy_hostname, proxy_port=proxy_port
            )

        # Register callbacks
        self.client.on_connect = self.on_connect


    def _fetch_robot_config(self):
        raise NotImplementedError()

    def on_connect(self, client, userdata, flags, rc):
        # Only assume that the robot is connected if return code is 0.
        # Other values are taken as errors (check here:
        # http://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html#_Toc398718035)
        # so connection process needs to be aborted.
        if rc == 0:
            self.logger.info("Connected to MQTT")
        else:
            self.logger.warn("Unable to connect. rc = {:d}.".format(rc))
            return

        # Send online status.
        # This method is blocking so do it on a separate thread just in case.
        threading.Thread(target=self.send_online_status).start()

        self.logger.debug("Connection thread executed")


    def send_online_status(self):
        """
        Sends online status message.
        NOTE: This method blocks until either the message is sent or
        the client errors out.
        """

        # Every time we connect to the service, send updated status,
        # including online bit
        status_message = "1|%s|%s|%s" % (self.app_key, self.agent_version, self.robot_name)
        ret = self.publish("r/%s/state" % self.robot_id, status_message, qos=1, retain=True)
        self.logger.info("Publishing online status. ret = {}.".format(ret))

        ret.wait_for_publish()
        published = ret.is_published()

        self.logger.info("Online status published: {:b}.".format(published))


    def connect(self):
        # TODO: call _fetch_robot_config. Assuming it returns a dict
        robot_config = {
            "hostname": "localdev.com",
            "port": 1883,
            "protocol": "mqtt://",
            "websocket_port": 9001,
            "websocket_protocol": "ws://",
            "username": "sikubotari",
            "password": "fo6E63Plyl21MWhJ",
            "robotApiKey": "H_2QCEQz6pD7i7xF",
        }

        self.client.username_pw_set(robot_config["username"], robot_config["password"])
        will_topic = "r/%s/state" % self.robot_id
        will_payload = "0|%s" % self.app_key
        self.client.will_set(will_topic, will_payload, qos=1, retain=True)

        if self.use_ssl:
            self.logger.debug("Configuring client to use SSL")
            self.client.tls_set(
                "/etc/ssl/certs/ca-certificates.crt", tls_version=ssl.PROTOCOL_TLSv1_2
            )
        
        hostname = robot_config["hostname"]
        port = robot_config["websockets_port"] if self.use_websocket else robot_config["port"]
        self.client.connect_async(hostname, port, keepalive=10)
        self.client.loop_start()

        self.logger.info("MQTT connection initiated. {}:{} ({})".format(
                hostname, port, 'websocket' if self.use_websocket else 'MQTT'
            ))


    def publish(self, topic, message, qos=0, retain=False):
        return self.client.publish(topic=topic, payload=message, qos=qos, retain=retain)
