#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
from unittest.mock import ANY, MagicMock

import pytest
from paho.mqtt.client import MQTTMessage

from inorbit_edge.inorbit_pb2 import (
    CustomCommandRosMessage,
    CustomScriptCommandMessage,
    Echo,
    MapRequest,
)
from inorbit_edge.robot import RobotSession
from inorbit_edge import get_module_version
from inorbit_edge.tests.utils.helpers import test_robot_session_connect_helper


def test_builtin_callbacks(mock_mqtt_client, mock_inorbit_api, mock_sleep):
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    # connect robot_session, so it populates properties with API response data
    robot_session.connect()
    robot_session._on_connect(None, None, None, 0, None)

    robot_session.client.subscribe.assert_any_call(topic="r/id_123/ros/loc/set_pose")
    robot_session.client.subscribe.assert_any_call(
        topic="r/id_123/custom_command/script/command"
    )
    robot_session.client.subscribe.assert_any_call(topic="r/id_123/custom_command/ros")
    robot_session.client.subscribe.assert_any_call(topic="r/id_123/ros/loc/nav_goal")
    robot_session.client.subscribe.assert_any_call(topic="r/id_123/in_cmd")
    robot_session.client.subscribe.assert_any_call(topic="r/id_123/ros/loc/mapreq")


def test_responds_to_get_state_with_default_online_status(
    mock_mqtt_client, mock_inorbit_api, mock_sleep
):
    """Test that get_state command responds with default online status."""
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )
    robot_session.connect()
    robot_session._on_connect(None, None, None, 0, None)

    # Simulate get_state command
    robot_session._handle_in_cmd(b"get_state")

    # Verify online status was published
    robot_session.client.publish.assert_any_call(
        "r/id_123/state",
        "1|robot_apikey_123|{}.edgesdk_py|name_123".format(get_module_version()),
        qos=1,
        retain=True,
    )


def test_responds_to_get_state_with_callback_online_status(
    mock_mqtt_client, mock_inorbit_api, mock_sleep
):
    """Test that get_state command uses callback for online status."""
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )
    robot_session.connect()
    robot_session._on_connect(None, None, None, 0, None)

    # Set callback that returns False (offline)
    robot_session.set_online_status_callback(lambda: False)

    # Simulate get_state command
    robot_session._handle_in_cmd(b"get_state")

    # Verify offline status was published
    robot_session.client.publish.assert_any_call(
        "r/id_123/state",
        "0|robot_apikey_123|{}.edgesdk_py|name_123".format(get_module_version()),
        qos=1,
        retain=True,
    )


def test_get_state_handles_callback_exception(
    mock_mqtt_client, mock_inorbit_api, mock_sleep
):
    """Test that get_state handles callback exceptions gracefully."""
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )
    robot_session.connect()
    robot_session._on_connect(None, None, None, 0, None)

    # Set callback that raises exception
    def failing_callback():
        raise RuntimeError("Test error")

    robot_session.set_online_status_callback(failing_callback)

    # Simulate get_state command - should not raise exception
    robot_session._handle_in_cmd(b"get_state")

    # Verify default online status was published despite callback error
    robot_session.client.publish.assert_any_call(
        "r/id_123/state",
        "1|robot_apikey_123|{}.edgesdk_py|name_123".format(get_module_version()),
        qos=1,
        retain=True,
    )


def test_set_online_status_callback_ignores_non_callable(
    mock_mqtt_client, mock_inorbit_api, mock_sleep
):
    """Test that set_online_status_callback ignores non-callable values."""
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )

    # Try to set non-callable
    robot_session.set_online_status_callback("not_callable")

    # Should remain None
    assert robot_session._online_status_callback is None


def test_robot_session_register_command_callback(
    mock_mqtt_client, mock_inorbit_api, mock_sleep
):
    my_command_handler = MagicMock()
    my_command_handler.__name__ = "my_command_handler"
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
    robot_session._on_connect(None, None, None, 0, None)

    msg = MQTTMessage(topic=b"r/id_123/custom_command/script/command")
    msg.payload = CustomScriptCommandMessage(
        file_name="foo", arg_options=["a", "b"], execution_id="1"
    ).SerializeToString()

    robot_session._on_message(None, None, msg)

    my_command_handler.assert_called_once_with(
        "customCommand",
        ["foo", ["a", "b"]],
        {
            "result_function": ANY,
            "progress_function": ANY,
            "metadata": {},
        },
    )


def test_robot_session_echo(mocker, mock_mqtt_client, mock_inorbit_api, mock_sleep):

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
    robot_session._on_connect(None, None, None, 0, None)

    msg = MQTTMessage(topic=b"r/id_123/ros/loc/set_pose")
    msg.payload = "1|123456789|1.23|4.56|-0.1".encode()

    mocker.patch.object(time, "time", return_value=123456.789)
    robot_session._on_message(None, None, msg)

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
                "command_args": [{"x": "1.23", "y": "4.56", "theta": "-0.1"}],
            },
        ),
        (
            {
                "topic": b"r/id_123/custom_command/script/command",
                "payload": CustomScriptCommandMessage(
                    file_name="foo", arg_options=["a", "b"], execution_id="1"
                ).SerializeToString(),
            },
            {"command_name": "customCommand", "command_args": ["foo", ["a", "b"]]},
        ),
        (
            {
                "topic": b"r/id_123/ros/loc/nav_goal",
                "payload": "1|123456789|1.23|4.56|-0.1".encode(),
            },
            {
                "command_name": "navGoal",
                "command_args": [{"x": "1.23", "y": "4.56", "theta": "-0.1"}],
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
    mock_mqtt_client, mock_inorbit_api, mock_sleep, test_input, expected
):
    # Mock command handler.
    my_command_handler = MagicMock()
    # Set command handler mock method's name as it's accessed by the RobotSession class
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
    robot_session._on_connect(None, None, None, 0, None)

    msg = MQTTMessage(topic=test_input["topic"])
    msg.payload = test_input["payload"]

    robot_session._on_message(None, None, msg)
    my_command_handler.assert_called_once_with(
        expected["command_name"],
        expected["command_args"],
        {
            "result_function": ANY,
            "progress_function": ANY,
            "metadata": {},
        },
    )


def test_robot_session_executes_commands(
    mock_mqtt_client, mock_inorbit_api, mock_popen, mock_sleep
):
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )

    robot_session.register_commands_path("./user_scripts", r".*\.sh")

    # Tests asserted here
    test_robot_session_connect_helper(robot_session, mock_popen)


def test_robot_session_handles_map_requests(
    mock_mqtt_client, mock_inorbit_api, mock_popen, mock_sleep
):
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    robot_session._send_map = MagicMock()

    # connect robot_session, so it populates properties with API response data
    robot_session.connect()
    # manually execute on_connect callback, so the ``custom_command_callback``
    # callback gets registered
    robot_session._on_connect(None, None, None, 0, None)

    msg = MQTTMessage(topic=b"r/id_123/ros/loc/mapreq")
    msg.payload = MapRequest(
        label="Test Map Label", data_hash=4565286020005755223
    ).SerializeToString()

    # test it doesn't publish if the map hasn't been published before
    robot_session._on_message(None, None, msg)
    robot_session.client._publish_map_bytes.assert_not_called()

    # test it publishes the map if it has been published before
    robot_session.publish_map(
        file=f"{os.path.dirname(__file__)}/utils/test_map.png",
        map_id="map_id",
        map_label="Test Map Label",
        frame_id="frame_id",
        x=1,
        y=2,
        resolution=0.005,
        ts=123,
        is_update=False,
        force_upload=False,
    )
    robot_session._send_map.assert_called_once()
    args1 = robot_session._send_map.call_args_list[0]
    assert args1.kwargs["include_pixels"] is False
    robot_session._on_message(None, None, msg)
    assert robot_session._send_map.call_count == 2
    args2 = robot_session._send_map.call_args_list[1]
    assert args2.kwargs["include_pixels"] is True

    # test it doesn't publish if the hash doesn't match
    msg.payload = MapRequest(label="map_id", data_hash=123).SerializeToString()
    robot_session._on_message(None, None, msg)
    robot_session.client._publish_map_bytes.assert_not_called()
