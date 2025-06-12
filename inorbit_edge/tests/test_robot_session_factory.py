#!/usr/bin/env python
# -*- coding: utf-8 -*-

from unittest.mock import MagicMock
from paho.mqtt.client import MQTTMessage
from inorbit_edge.robot import RobotSessionFactory
from inorbit_edge.inorbit_pb2 import CustomScriptCommandMessage
from inorbit_edge.tests.utils.helpers import test_robot_session_connect_helper


def test_robot_factory_build(mock_mqtt_client, mock_sleep):
    robot_session_factory = RobotSessionFactory(
        api_key="apikey_123", endpoint="http://myendpoint/"
    )
    robot_session = robot_session_factory.build("id_123", "name_123")

    assert all(
        [
            robot_session.robot_id == "id_123",
            robot_session.robot_name == "name_123",
            robot_session.api_key == "apikey_123",
            robot_session.agent_version.endswith("edgesdk_py"),
            robot_session.endpoint == "http://myendpoint/",
            robot_session.http_proxy is None,
        ]
    )

    # Robot session launched using a robot key for authentication. The robot
    # key and name are specified as kwargs.
    robot_session = robot_session_factory.build(
        "id_123", **{"robot_name": "name_123", "robot_key": "robotkey_123"}
    )

    assert all(
        [
            robot_session.robot_id == "id_123",
            robot_session.robot_name == "name_123",
            robot_session.robot_key == "robotkey_123",
            robot_session.agent_version.endswith("edgesdk_py"),
            robot_session.endpoint == "http://myendpoint/",
            robot_session.http_proxy is None,
        ]
    )

    # Robot session launched using an API key for authentication. The robot name
    # is specified as a kwarg.
    robot_session_factory = RobotSessionFactory(
        api_key="apikey_123", endpoint="http://myendpoint/"
    )

    robot_session = robot_session_factory.build("id_456", **{"robot_name": "name_456"})

    assert all(
        [
            robot_session.robot_id == "id_456",
            robot_session.robot_name == "name_456",
            robot_session.api_key == "apikey_123",
            robot_session.agent_version.endswith("edgesdk_py"),
            robot_session.endpoint == "http://myendpoint/",
            robot_session.http_proxy is None,
        ]
    )


def test_built_robot_session_executes_command_callback_on_message(
    mock_mqtt_client, mock_inorbit_api, mock_sleep
):
    # Mock command handler.
    my_command_handler = MagicMock()
    another_command_handler = MagicMock()
    # Set command handler mock method's name as it's accessed by the RobotSession class
    my_command_handler.configure_mock(**{"__name__": "my_command_handler"})
    another_command_handler.configure_mock(**{"__name__": "another_command_handler"})

    robot_session_factory = RobotSessionFactory(api_key="apikey_123")
    robot_session_factory.register_command_callback(another_command_handler)
    robot_session_factory.register_command_callback(my_command_handler)

    robot_session = robot_session_factory.build("id_123", "name_123")

    # connect robot_session, so it populates properties with API response data
    robot_session.connect()
    # manually execute on_connect callback so the ``custom_command_callback``
    # callback gets registered
    robot_session._on_connect(None, None, None, 0, None)

    msg = MQTTMessage(topic=b"r/id_123/custom_command/script/command")
    msg.payload = CustomScriptCommandMessage(
        file_name="foo", arg_options=["a", "b"], execution_id="1"
    ).SerializeToString()

    robot_session._on_message(None, None, msg)

    _test_command_handler_helper(my_command_handler)
    _test_command_handler_helper(another_command_handler)


def _test_command_handler_helper(command_handler):
    command_handler.assert_called_once()
    call_args, call_kwargs = command_handler.call_args_list[0]

    # No kwargs are expected
    assert not call_kwargs

    [robot_id, command_name, command_args, command_options] = call_args
    assert robot_id == "id_123"
    assert command_name == "customCommand"
    assert command_args == ["foo", ["a", "b"]]
    assert callable(command_options["result_function"])
    assert callable(command_options["progress_function"])
    assert command_options["metadata"] == {}


def test_built_robot_session_executes_commands(
    mock_mqtt_client, mock_inorbit_api, mock_popen, mock_sleep
):
    robot_session_factory = RobotSessionFactory(api_key="apikey_123")
    robot_session_factory.register_commands_path("./user_scripts", r".*\.sh")

    robot_session = robot_session_factory.build("id_123", "name_123")

    # Tests asserted here
    test_robot_session_connect_helper(robot_session, mock_popen)
