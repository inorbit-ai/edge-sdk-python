#!/usr/bin/env python
# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch
from paho.mqtt.client import MQTTMessage
from inorbit_edge.robot import RobotSessionFactory
from inorbit_edge.inorbit_pb2 import CustomScriptCommandMessage


def test_robot_factory_build(mock_mqtt_client):
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


def test_built_robot_session_executes_command_callback_on_message(
    mock_mqtt_client, mock_inorbit_api
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

    # connect robot_session so it populates properties with API response data
    robot_session.connect()
    # manually execute on_connect callback so the ``custom_command_callback``
    # callback gets registered
    robot_session._on_connect(..., ..., ..., 0)

    msg = MQTTMessage(topic=b"r/id_123/custom_command/script/command")
    msg.payload = CustomScriptCommandMessage(
        file_name="foo", arg_options=["a", "b"], execution_id="1"
    ).SerializeToString()

    robot_session._on_message(..., ..., msg)

    my_command_handler.assert_called_once()
    call_args, call_kwargs = my_command_handler.call_args_list[0]

    # No kwargs are expected
    assert not call_kwargs

    [robot_id, command_name, command_args, command_options] = call_args
    assert robot_id == "id_123"
    assert command_name == "customCommand"
    assert command_args == ["foo", ["a", "b"]]
    assert callable(command_options["result_function"])
    assert callable(command_options["progress_function"])
    assert command_options["metadata"] == {}

    another_command_handler.assert_called_once()
    call_args, call_kwargs = another_command_handler.call_args_list[0]

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
    mock_mqtt_client, mock_inorbit_api, mock_popen
):
    robot_session_factory = RobotSessionFactory(api_key="apikey_123")
    robot_session_factory.register_executable_commands(r".*\.sh", "./user_scripts")

    robot_session = robot_session_factory.build("id_123", "name_123")

    # connect robot_session so it populates properties with API response data
    robot_session.connect()
    # manually execute on_connect callback so the ``custom_command_callback``
    # callback gets registered
    robot_session._on_connect(..., ..., ..., 0)

    msg = MQTTMessage(topic=b"r/id_123/custom_command/script/command")
    msg.payload = CustomScriptCommandMessage(
        file_name="my_script.sh", arg_options=["a", "b"], execution_id="1"
    ).SerializeToString()

    robot_session._on_message(..., ..., msg)

    mock_popen.assert_called_once()
    call_args, call_kwargs = mock_popen.call_args_list[0]

    [program_args] = call_args
    assert program_args == ["./user_scripts/my_script.sh", "a", "b"]
    assert call_kwargs["env"]["INORBIT_ROBOT_ID"] == "id_123"
