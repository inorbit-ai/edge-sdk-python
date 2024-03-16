# Tests the missions functionalities
#
# TODO(mike) add tests for wait event step
# TODO(mike) add tests cancel()

from inorbit_edge.robot import (
    RobotSession,
    COMMAND_MESSAGE,
    COMMAND_CUSTOM_COMMAND,
    COMMAND_NAV_GOAL,
)


def test_mission_end_to_end(
    mock_mqtt_client, mock_inorbit_api, mocker, mock_sleep, mock_time
):
    """Tests mission execution and tracking"""
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )

    # Mock command handler.
    my_command_handler = mocker.MagicMock()
    # Set command handler mock method's name as it's accessed by the RobotSession class
    my_command_handler.configure_mock(**{"__name__": "my_command_handler"})
    robot_session.publish_key_values = mocker.MagicMock()
    robot_session.register_command_callback(my_command_handler)
    # Set this pose so the goto waypoint step succeeds
    robot_session.publish_pose(10, 15.5, 0.5, "map")
    message = """inorbit_run_mission 1234
    {
      "label": "Delivery Mission",
      "steps": [
        {
          "type": "SetData",
          "label": "init data",
          "data": {
            "order": "#321",
            "items": ["InOrbito", "Bottle"]
          }
        },
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
          "seconds": 1.32
        },
        {
          "type": "Action",
          "label": "go to picking station",
          "action": {
            "type": "NavigateTo",
            "waypoint": { "x": 10, "y": 15.5, "theta": 0.5, "frameId": "map" }
          },
          "tolerance": { "positionMeters": 0.05, "angularRadians": 0.25 }
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
    robot_session.dispatch_command(COMMAND_MESSAGE, [message])
    # wait for mission completion
    assert robot_session.missions_module.executor.wait_until_idle(10)
    # filter out the execute mission command
    dispatched_commands = [
        c
        for c in my_command_handler.call_args_list
        if c[0][0] != COMMAND_MESSAGE or c[0][1][0] != message
    ]
    # check step completed and message published
    call_args, _ = dispatched_commands[0]
    [command_name, command_args, _] = call_args
    assert command_name == COMMAND_MESSAGE
    assert command_args == ["hello world"]
    # check step completed and another message published
    call_args, _ = dispatched_commands[1]
    [command_name, command_args, _] = call_args
    assert command_name == COMMAND_MESSAGE
    assert command_args == ["hello world 2"]
    # check that navigate step sends navGoal command
    call_args, _ = dispatched_commands[2]
    [command_name, command_args, _] = call_args
    assert command_name == COMMAND_NAV_GOAL
    assert command_args == [{"x": 10, "y": 15.5, "theta": 0.5, "frameId": "map"}]
    # check that the script step dispatches the script for execution
    call_args, _ = dispatched_commands[3]
    [command_name, command_args, _] = call_args
    assert command_name == COMMAND_CUSTOM_COMMAND
    assert command_args == ["turn_on_beep.sh", ["arg1", "arg2"]]

    # check mission tracking reports
    reports = [
        c[1]["key_values"]["mission_tracking"]
        for c in robot_session.publish_key_values.call_args_list
        if "key_values" in c[1] and "mission_tracking" in c[1]["key_values"]
    ]
    expected_tasks = [
        {"label": "init data", "taskId": "0"},
        {"label": "my step", "taskId": "1"},
        {"label": "my step 2", "taskId": "2"},
        {"label": "sleep", "taskId": "3"},
        {"label": "go to picking station", "taskId": "4"},
        {"label": "run a script", "taskId": "5"},
    ]
    expected_reports = [
        {
            "missionId": "1234\n",
            "inProgress": True,
            "currentTaskId": "0",
            "state": "Executing",
            "label": "Delivery Mission",
            "startTs": mock_time.return_value * 1000,
            "data": {"order": "#321", "items": ["InOrbito", "Bottle"]},
            "status": "OK",
            "completedPercent": 0.0,
            "tasks": expected_tasks,
        },
        {
            "missionId": "1234\n",
            "inProgress": True,
            "currentTaskId": "1",
            "state": "Executing",
            "label": "Delivery Mission",
            "startTs": mock_time.return_value * 1000,
            "data": {"order": "#321", "items": ["InOrbito", "Bottle"]},
            "status": "OK",
            "completedPercent": 0.16666666666666666,
            "tasks": expected_tasks,
        },
        {
            "missionId": "1234\n",
            "inProgress": True,
            "currentTaskId": "2",
            "state": "Executing",
            "label": "Delivery Mission",
            "startTs": mock_time.return_value * 1000,
            "data": {"order": "#321", "items": ["InOrbito", "Bottle"]},
            "status": "OK",
            "completedPercent": 0.3333333333333333,
            "tasks": expected_tasks,
        },
        {
            "missionId": "1234\n",
            "inProgress": True,
            "currentTaskId": "3",
            "state": "Executing",
            "label": "Delivery Mission",
            "startTs": mock_time.return_value * 1000,
            "data": {"order": "#321", "items": ["InOrbito", "Bottle"]},
            "status": "OK",
            "completedPercent": 0.5,
            "tasks": expected_tasks,
        },
        {
            "missionId": "1234\n",
            "inProgress": True,
            "currentTaskId": "4",
            "state": "Executing",
            "label": "Delivery Mission",
            "startTs": mock_time.return_value * 1000,
            "data": {"order": "#321", "items": ["InOrbito", "Bottle"]},
            "status": "OK",
            "completedPercent": 0.6666666666666666,
            "tasks": expected_tasks,
        },
        {
            "missionId": "1234\n",
            "inProgress": True,
            "currentTaskId": "5",
            "state": "Executing",
            "label": "Delivery Mission",
            "startTs": mock_time.return_value * 1000,
            "data": {"order": "#321", "items": ["InOrbito", "Bottle"]},
            "status": "OK",
            "completedPercent": 0.8333333333333334,
            "tasks": expected_tasks,
        },
        {
            "missionId": "1234\n",
            "inProgress": False,
            "state": "Completed",
            "label": "Delivery Mission",
            "startTs": mock_time.return_value * 1000,
            "endTs": mock_time.return_value * 1000,
            "data": {"order": "#321", "items": ["InOrbito", "Bottle"]},
            "status": "OK",
            "completedPercent": 1.0,
            "tasks": expected_tasks,
        },
    ]
    assert reports == expected_reports
