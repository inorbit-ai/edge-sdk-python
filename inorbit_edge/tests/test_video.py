#!/usr/bin/env python
# -*- coding: utf-8 -*-

from inorbit_edge.robot import RobotSession
from inorbit_edge.video import OpenCVCamera
from inorbit_edge.robot import INORBIT_MODULE_CAMERAS


def test_robot_session_register_camera(mock_mqtt_client, mock_inorbit_api, mocker, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda x: None)
    camera_id = "cam0"
    runlevel = 0

    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )
    robot_session.connect()

    # TODO: Improve OpenCVCamera test. This `video_url` parameter causes an OpenCV
    # exception "error: (-215:Assertion failed) !_filename.empty() in function 'open'"
    # This is fine for the purpose of this test that is verify that the Capture and
    # Camera stream threads stop when the robot session disconnects.
    opencv_camera = OpenCVCamera(None, rate=8, scaling=0.2, quality=35)
    robot_session.register_camera(camera_id, opencv_camera)

    camera_stream = robot_session.camera_streamers[camera_id]
    # Register spies for test assertions
    stop_cameras_streaming_spy = mocker.spy(robot_session, "_stop_cameras_streaming")
    camera_stream_stop_spy = mocker.spy(camera_stream, "stop")
    opencv_camera_close_spy = mocker.spy(opencv_camera, "close")
    # Simulate cmd to start camera stream
    robot_session._handle_in_cmd(
        f"load_module|{INORBIT_MODULE_CAMERAS}|{runlevel}".encode()
    )
    # Override _is_disconnected method to simulate successful MQTT client disconnection
    robot_session._is_disconnected = lambda: True
    robot_session.disconnect()

    stop_cameras_streaming_spy.assert_called_once()
    camera_stream_stop_spy.assert_called_once()
    opencv_camera_close_spy.assert_called_once()

    # Verify threads are stopped
    assert not camera_stream.thread.is_alive()
    assert not opencv_camera.capture_thread.is_alive()
