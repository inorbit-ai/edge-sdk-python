#!/usr/bin/env python
# -*- coding: utf-8 -*-

from paho.mqtt.client import MQTTMessage

from inorbit_edge.inorbit_pb2 import CustomScriptCommandMessage


def test_robot_session_connect_helper(robot_session=None, mock_popen=None):
    """A helper function to connect and verify callback data"""

    # Prevents running the test if nothing is provided. This allows marking
    # the function as in the scope of a test which has different linting rules
    # (e.g., allowing access to protected functions).
    if (robot_session is None) or (mock_popen is None):
        return

    # connect robot_session, so it populates properties with API response data
    robot_session.connect()
    # manually execute on_connect callback so the ``custom_command_callback``
    # callback gets registered
    robot_session._on_connect(None, None, None, 0, None)

    msg = MQTTMessage(topic=b"r/id_123/custom_command/script/command")
    msg.payload = CustomScriptCommandMessage(
        file_name="my_script.sh", arg_options=["a", "b"], execution_id="1"
    ).SerializeToString()

    robot_session._on_message(None, None, msg)

    mock_popen.assert_called_once()
    call_args, call_kwargs = mock_popen.call_args_list[0]

    [program_args] = call_args
    assert program_args == ["./user_scripts/my_script.sh", "a", "b"]
    assert call_kwargs["env"]["INORBIT_ROBOT_ID"] == "id_123"
