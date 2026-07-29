#!/usr/bin/env python
# -*- coding: utf-8 -*-

import threading
import time

import cv2
import numpy

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


class FakeCapture:
    """Minimal cv2.VideoCapture double that counts grabs and retrieves."""

    def __init__(self, grab_ok=False, frame=None, delay=0.0):
        self.grab_ok = grab_ok
        self.frame = frame
        self.delay = delay
        self.grabs = 0
        self.retrieves = 0
        self.released = False

    def grab(self):
        self.grabs += 1
        if self.delay:
            time.sleep(self.delay)  # a real grab is paced by the stream
        return self.grab_ok

    def retrieve(self):
        self.retrieves += 1
        return self.frame is not None, self.frame

    def release(self):
        self.released = True


def test_failed_grab_reopens_the_capture_without_spinning(mocker):
    """A dead stream must be backed off and rebuilt, not spun on."""
    camera = OpenCVCamera("rtsp://camera.invalid/stream", rate=1)
    camera.REOPEN_BACKOFF_SECONDS = (0.05,)
    captures = []

    def fake_open_capture():
        captures.append(FakeCapture(grab_ok=False))
        return captures[-1]

    mocker.patch.object(camera, "_open_capture", side_effect=fake_open_capture)

    camera.open()
    try:
        time.sleep(0.3)
    finally:
        camera.close()

    # Unpaced, a failing grab() runs hundreds of thousands of times in 0.3s and
    # pegs a core; with the backoff it stays in the single digits per capture.
    assert sum(capture.grabs for capture in captures) < 25
    assert len(captures) > 1, "capture was never reopened"
    assert captures[0].released


def test_frames_are_decoded_at_the_publish_rate_not_the_stream_rate(mocker):
    """Every frame is drained with grab(); only published ones are decoded."""
    frame = numpy.zeros((16, 16, 3), dtype=numpy.uint8)
    capture = FakeCapture(grab_ok=True, frame=frame, delay=0.002)
    camera = OpenCVCamera("rtsp://camera.invalid/stream", rate=1, scaling=0.5)
    mocker.patch.object(camera, "_open_capture", return_value=capture)

    camera.open()
    try:
        time.sleep(0.6)
        jpg, _w, _h, _ts = camera.get_frame_jpg()
        retrieves_after_publishing = capture.retrieves
    finally:
        camera.close()

    assert capture.grabs > 20
    assert retrieves_after_publishing <= 3, "decoding every grabbed frame"
    assert jpg is not None
    # Publishing reads the buffered frame; it never touches the capture.
    assert capture.retrieves == retrieves_after_publishing


def test_get_frame_jpg_returns_no_frame_while_the_capture_is_reopening():
    camera = OpenCVCamera("rtsp://camera.invalid/stream", rate=1)

    jpg, width, height, _ts = camera.get_frame_jpg()

    assert jpg is None and (width, height) == (0, 0)


def test_url_sources_request_the_ffmpeg_backend(mocker):
    """OPENCV_FFMPEG_CAPTURE_OPTIONS only applies to the FFmpeg backend."""
    video_capture = mocker.patch("cv2.VideoCapture")

    OpenCVCamera("rtsp://camera.invalid/stream")._open_capture()
    assert video_capture.call_args.args[1] == cv2.CAP_FFMPEG

    OpenCVCamera("/dev/video0")._open_capture()
    assert video_capture.call_args.args[1] == cv2.CAP_ANY

    OpenCVCamera(
        "rtsp://camera.invalid/stream", api_preference=cv2.CAP_GSTREAMER
    )._open_capture()
    assert video_capture.call_args.args[1] == cv2.CAP_GSTREAMER


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
