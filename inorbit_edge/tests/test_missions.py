from unittest.mock import MagicMock
from inorbit_edge.robot import RobotSession, COMMAND_MESSAGE, COMMAND_CUSTOM_COMMAND

def test_mission_end_to_end(mock_mqtt_client, mock_inorbit_api, mocker):
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )
    # Mock command handler.
    my_command_handler = MagicMock()
    # Set command handler mock method's name as it's accessed by the RobotSession class
    my_command_handler.configure_mock(**{"__name__": "my_command_handler"})
    robot_session.register_command_callback(my_command_handler)
    message = """inorbit_run_mission 1234 
    {
      "steps": [
        { 
          "type": "Action",
          "label": "my step",
          "action": {
            "type": "PublishToTopic",
            "message": "hello world"
          }
        },
        { 
          "type": "Action",
          "label": "my step 2",
          "action": {
            "type": "PublishToTopic",
            "message": "hello world 2"
          }
        },
        { 
          "type": "WaitSeconds",
          "label": "sleep",
          "seconds": 1.5
        },
        { 
          "type": "Action",
          "label": "run a script",
          "action": {
            "type": "RunScript",
            "fileName": "turn_on_beep.sh",
            "args": ["arg1", "arg2"]
          }
        }
      ]
    }
    """
    # run mission
    robot_session.dispatch_command(COMMAND_MESSAGE, message)
    # wait for mission completion
    robot_session.missions_module.executor.wait_until_idle(5)

    # filter out the execute mission command
    dispatched_commands = [c for c in my_command_handler.call_args_list
      if c.args[0] != COMMAND_MESSAGE or c.args[1] != message]
      
    # check that the 1st step completed
    call_args, _ = dispatched_commands[0]
    [command_name, command_args, _] = call_args
    assert command_name == COMMAND_MESSAGE
    assert command_args == "hello world"
    # check that the 2nd step completed
    call_args, _ = dispatched_commands[1]
    [command_name, command_args, _] = call_args
    assert command_name == COMMAND_MESSAGE
    assert command_args == "hello world 2"
    # check that the 3nd step completed
    call_args, _ = dispatched_commands[2]
    [command_name, command_args, _] = call_args
    assert command_name == COMMAND_CUSTOM_COMMAND
    assert command_args == ["turn_on_beep.sh", ["arg1", "arg2"]]

