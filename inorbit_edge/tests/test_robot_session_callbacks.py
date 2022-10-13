#!/usr/bin/env python
# -*- coding: utf-8 -*-

from inorbit_edge.robot import RobotSession
from paho.mqtt.client import MQTTMessage
from inorbit_edge.inorbit_pb2 import Echo
import time

def test_builtin_callbacks(mock_mqtt_client, mock_inorbit_api):
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    # connect robot_session so it populates properties with API response data
    robot_session.connect()
    robot_session._on_connect(..., ..., ..., 0)

    robot_session.client.subscribe.assert_any_call(
        topic="r/id_123/ros/loc/set_pose"
    )
    robot_session.client.subscribe.assert_any_call(
        topic="r/id_123/custom_command/script/command"
    )
    robot_session.client.subscribe.call_count == 2


def test_robot_session_custom_command_callback(mock_mqtt_client, mock_inorbit_api):
    def my_command_handler(command_name, args, options):
        pass

    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    robot_session.register_command_callback(my_command_handler)

    # connect robot_session so it populates properties with API response data
    robot_session.connect()
    # manually execute on_connect callback so the ``custom_command_callback``
    # callback gets registered
    robot_session._on_connect(..., ..., ..., 0)

    assert my_command_handler in robot_session.command_callbacks
    robot_session.client.subscribe.assert_called_with(
        topic="r/id_123/custom_command/script/command"
    )


def test_robot_session_callback_on_message(mocker, mock_mqtt_client, mock_inorbit_api):
    def my_command_handler(command_name, args, options):
        pass

    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    robot_session.register_command_callback(my_command_handler)

    # connect robot_session so it populates properties with API response data
    robot_session.connect()
    # manually execute on_connect callback so the ``custom_command_callback``
    # callback gets registered
    robot_session._on_connect(..., ..., ..., 0)

    msg = MQTTMessage(topic=b"r/id_123/ros/loc/set_pose")
    msg.payload = "1|123456789|1.23|4.56|-0.1".encode()
    
    with mocker.patch.object(time, "time", return_value=123456.789):
        robot_session._on_message(..., ..., msg)

        echo_msg = Echo()
        echo_msg.topic = "r/id_123/ros/loc/set_pose"
        echo_msg.time_stamp = int(time.time() * 1000)
        echo_msg.string_payload = msg.payload.decode("utf-8", errors="ignore")

    robot_session.client.publish.assert_any_call(
        topic="r/id_123/echo",
        payload=bytearray(echo_msg.SerializeToString()),
        qos=0,
        retain=False
    )