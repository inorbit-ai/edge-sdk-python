#!/usr/bin/env python
# -*- coding: utf-8 -*-

import threading
import time

from inorbit_edge.robot import RobotSession
from inorbit_edge.video import CameraStreamer, OpenCVCamera
from inorbit_edge.robot import INORBIT_MODULE_CAMERAS


def _wait_until(predicate, timeout=2.0):
    """Poll ``predicate`` until it is truthy or ``timeout`` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


class FakeCamera:
    """Minimal Camera double that records open/close calls without touching cv2."""

    rate = 50

    def __init__(self):
        self._lock = threading.Lock()
        self.opens = 0
        self.closes = 0

    def open(self):
        with self._lock:
            self.opens += 1

    def close(self):
        with self._lock:
            self.closes += 1

    def get_frame_jpg(self):
        return None, 0, 0, 0


def test_robot_session_register_camera(
    mock_mqtt_client, mock_inorbit_api, mocker, mock_sleep
):
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
    # The worker opens the camera asynchronously; wait until it has actually
    # started before tearing down, so teardown has a live session to close.
    assert _wait_until(lambda: opencv_camera.capture_thread is not None, timeout=5)
    # Override _is_disconnected method to simulate successful MQTT client disconnection
    robot_session._is_disconnected = lambda: True
    robot_session.disconnect()

    stop_cameras_streaming_spy.assert_called_once()
    camera_stream_stop_spy.assert_called_once()
    opencv_camera_close_spy.assert_called_once()

    # disconnect() shuts down and joins the worker, so it must be gone. Join again
    # with a timeout to keep the assertion non-flaky regardless of scheduling.
    camera_stream.join(timeout=15)
    assert not camera_stream.is_alive()
    if opencv_camera.capture_thread is not None:
        opencv_camera.capture_thread.join(timeout=10)
        assert not opencv_camera.capture_thread.is_alive()


def test_camera_streamer_start_stop_start_keeps_single_worker():
    """A stop->start cycle resumes streaming on the same single worker thread."""
    camera = FakeCamera()
    streamer = CameraStreamer(camera, lambda *args: None)
    worker = streamer._worker
    try:
        streamer.start()
        assert _wait_until(lambda: camera.opens >= 1)

        streamer.stop()
        assert _wait_until(lambda: camera.closes >= 1)

        streamer.start()
        assert _wait_until(lambda: camera.opens >= 2)

        # Same worker thread throughout -- no respawn, no ghost/duplicate.
        assert streamer._worker is worker
        assert streamer.is_alive()
    finally:
        streamer.shutdown()
        streamer.join(timeout=5)
        assert not streamer.is_alive()


def test_camera_streamer_shutdown_terminates_worker():
    camera = FakeCamera()
    streamer = CameraStreamer(camera, lambda *args: None)
    streamer.start()
    assert _wait_until(lambda: camera.opens >= 1)

    streamer.shutdown()
    streamer.join(timeout=5)
    assert not streamer.is_alive()
    # The camera is released on the way out.
    assert _wait_until(lambda: camera.closes >= 1)


def test_register_camera_twice_replaces_and_shuts_down_old(
    mock_mqtt_client, mock_inorbit_api, mocker, mock_sleep
):
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )
    camera_id = "cam0"

    # Streaming is off (no load_module), so workers stay idle -- no cv2 open.
    robot_session.register_camera(camera_id, OpenCVCamera(None))
    first = robot_session.camera_streamers[camera_id]

    robot_session.register_camera(camera_id, OpenCVCamera(None))
    second = robot_session.camera_streamers[camera_id]

    assert second is not first
    first.join(timeout=5)
    assert not first.is_alive()  # old streamer's worker was shut down
    assert second.is_alive()

    second.shutdown()
    second.join(timeout=5)
