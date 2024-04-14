#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
from unittest.mock import MagicMock, call

import pytest
from paho.mqtt.client import MQTTMessage

from inorbit_edge.inorbit_pb2 import CustomScriptCommandMessage, \
    CustomCommandRosMessage
from inorbit_edge.inorbit_pb2 import Echo
from inorbit_edge.robot import RobotSession
from inorbit_edge.tests.utils.helpers import test_robot_session_connect_helper


def test_builtin_callbacks(mock_mqtt_client, mock_inorbit_api):
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    # connect robot_session, so it populates properties with API response data
    robot_session.connect()
    robot_session._on_connect(..., ..., ..., 0)

    robot_session.client.subscribe.assert_any_call(
        topic="r/id_123/ros/loc/set_pose")
    robot_session.client.subscribe.assert_any_call(
        topic="r/id_123/custom_command/script/command"
    )


def test_robot_session_register_command_callback(mock_mqtt_client,
                                                 mock_inorbit_api):
    def my_command_handler(*_):
        pass

    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    robot_session.register_command_callback(my_command_handler)

    # connect robot_session, so it populates properties with API response data
    robot_session.connect()
    # manually execute on_connect callback, so the ``custom_command_callback``
    # callback gets registered
    robot_session._on_connect(..., ..., ..., 0)

    assert my_command_handler in robot_session.command_callbacks
    robot_session.client.subscribe.assert_has_calls(
        [
            call(topic="r/id_123/ros/loc/set_pose"),
            call(topic="r/id_123/custom_command/script/command"),
            call(topic="r/id_123/custom_command/ros"),
            call(topic="r/id_123/ros/loc/nav_goal"),
            call(topic="r/id_123/in_cmd"),
        ]
    )
    assert robot_session.client.subscribe.call_count == 5


def test_robot_session_echo(mocker, mock_mqtt_client, mock_inorbit_api):
    def my_command_handler(*_):
        pass

    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    robot_session.register_command_callback(my_command_handler)

    # connect robot_session, so it populates properties with API response data
    robot_session.connect()
    # manually execute on_connect callback, so the ``custom_command_callback``
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
        retain=False,
    )


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (
                {
                    "topic": b"r/id_123/ros/loc/set_pose",
                    "payload": "1|123456789|1.23|4.56|-0.1".encode(),
                },
                {
                    "command_name": "initialPose",
                    "command_args": [
                        {"x": "1.23", "y": "4.56", "theta": "-0.1"}],
                },
        ),
        (
                {
                    "topic": b"r/id_123/custom_command/script/command",
                    "payload": CustomScriptCommandMessage(
                        file_name="foo", arg_options=["a", "b"],
                        execution_id="1"
                    ).SerializeToString(),
                },
                {"command_name": "customCommand",
                 "command_args": ["foo", ["a", "b"]]},
        ),
        (
                {
                    "topic": b"r/id_123/ros/loc/nav_goal",
                    "payload": "1|123456789|1.23|4.56|-0.1".encode(),
                },
                {
                    "command_name": "navGoal",
                    "command_args": [
                        {"x": "1.23", "y": "4.56", "theta": "-0.1"}],
                },
        ),
        (
                {
                    "topic": b"r/id_123/custom_command/ros",
                    "payload": CustomCommandRosMessage(
                        cmd="hello world"
                    ).SerializeToString(),
                },
                {"command_name": "message", "command_args": ["hello world"]},
        ),
    ],
)
def test_robot_session_executes_command_callback_on_message(
        mock_mqtt_client, mock_inorbit_api, test_input, expected
):
    # Mock command handler.
    my_command_handler = MagicMock()
    # Set command handler mock method's name as it's accessed RobotSession
    my_command_handler.configure_mock(**{"__name__": "my_command_handler"})

    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    robot_session.register_command_callback(my_command_handler)

    # connect robot_session, so it populates properties with API response data
    robot_session.connect()
    # manually execute on_connect callback, so the ``custom_command_callback``
    # callback gets registered
    robot_session._on_connect(..., ..., ..., 0)

    msg = MQTTMessage(topic=test_input["topic"])
    msg.payload = test_input["payload"]

    robot_session._on_message(..., ..., msg)

    my_command_handler.assert_called_once()
    call_args, call_kwargs = my_command_handler.call_args_list[0]

    # No kwargs are expected
    assert not call_kwargs

    [command_name, command_args, command_options] = call_args
    assert command_name == expected["command_name"]
    assert command_args == expected["command_args"]
    # `command_options` is an object that contains two local methods (see
    # `RobotSession._dispatch_command` method), so given they cannot be
    # referenced, only check if values are callable
    assert callable(command_options["result_function"])
    assert callable(command_options["progress_function"])
    assert command_options["metadata"] == {}


def test_robot_session_executes_commands(
        mock_mqtt_client, mock_inorbit_api, mock_popen
):
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )

    robot_session.register_commands_path("./user_scripts", r".*\.sh")

    # Tests asserted here
    test_robot_session_connect_helper(robot_session, mock_popen)
