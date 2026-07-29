# This module provides video capturing capabilities. It allows to stream images from
# cameras, RTSP streams and more (everything support by OpenCV) to the InOrbit Platform.
#
# The functionality is split into two kind of classes:
# * Cameras: Take care of getting frames from a video source, like a webcam, file or
#   stream.
# * CameraStreamer: Consumes frames from a camera and send them to the platform.
#
# Future improvements / TODOs:
#   * Honor module states camera settings, like rate, size and quality.
#   * Decouple CameraStreamer from image processing and move it to robot.py
#   * Complete type annotations

import logging
import threading
import time
from abc import ABC, abstractmethod

try:
    import cv2
except Exception:
    logging.getLogger(__name__).warning(
        "Could not import cv2. Video support won't work"
    )


class Camera(ABC):
    """Interface that all camera classes must implement"""

    @abstractmethod
    def open(self):
        """Opens the capturing device / stream"""
        pass

    @abstractmethod
    def close(self):
        """Closes the capturing device / stream"""
        pass

    @abstractmethod
    def get_frame_jpg(self):
        """Returns the latest frame captured by the camera as a JPG image"""
        pass


def convert_frame(frame, width, height, scaling, quality=25):
    """Converts a frame to JPG"""
    w = int(width * scaling)
    h = int(height * scaling)
    resized = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
    img_encode = cv2.imencode(
        ".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    )[1].tobytes()
    return img_encode, w, h


class OpenCVCamera(Camera):
    """Camera implementation backed up by OpenCV

    A stream that goes away (camera reboot, network blip, RTSP session timeout)
    is reopened with backoff, so video comes back without restarting the
    connector.

    For URL sources the FFmpeg backend is requested explicitly, because
    automatic backend selection may pick another one and silently ignore
    ``OPENCV_FFMPEG_CAPTURE_OPTIONS`` -- where deployments set the RTSP
    transport and, importantly, the socket timeout that bounds a stalled read
    (``rtsp_transport;tcp|timeout;3000000``). Without a timeout OpenCV waits on
    its 30s watchdog before a dead stream is even noticed.
    """

    #: Delay before each reopen attempt, indexed by consecutive failed grabs.
    REOPEN_BACKOFF_SECONDS = (0.5, 1.0, 2.0, 5.0, 10.0)

    def __init__(
        self, video_url, rate=10, scaling=0.3, quality=35, api_preference=None
    ):
        # Cast to string to support URL objects
        self.video_url = str(video_url)
        self.capture = None
        self.capture_mutex = threading.Lock()
        self.capture_thread = None
        self.running = False
        self.logger = logging.getLogger(__class__.__name__)
        self.rate = rate
        self.scaling = scaling
        self.quality = quality
        self.api_preference = api_preference
        # Set by close() so a capture thread waiting out a reopen backoff wakes
        # up immediately instead of holding up teardown.
        self._closing = threading.Event()
        # Latest decoded frame as (frame, monotonic timestamp). Published by the
        # capture thread, read by get_frame_jpg(); a reference assignment is
        # atomic under the GIL, so no lock is involved.
        self._frame = None
        # grab() decodes the frame; retrieve() adds the YUV->BGR conversion and a
        # copy on top (4.5ms vs 7.1ms per frame at 1080p). Only one frame per
        # publish is ever used, so convert at twice the publish rate and let the
        # rest of the stream drain through grab() alone.
        self._retrieve_interval = 0.5 / max(rate, 1)

    def _open_capture(self):
        """Return a new ``cv2.VideoCapture`` for this camera's source."""
        preference = self.api_preference
        if preference is None:
            preference = cv2.CAP_FFMPEG if "://" in self.video_url else cv2.CAP_ANY
        return cv2.VideoCapture(self.video_url, preference)

    def open(self):
        """Opens the capturing device / stream"""
        self._closing.clear()
        self._frame = None
        with self.capture_mutex:
            if self.capture is None:
                self.capture = self._open_capture()
            if not self.running:
                self.running = True
                self.capture_thread = threading.Thread(target=self._run, daemon=True)
                self.capture_thread.start()

    def close(self):
        """Closes the capturing device / stream"""
        self.running = False
        self._closing.set()

        if self.capture_thread is not None:
            self.logger.info("Waiting for the capture thread to finish")
            self.capture_thread.join()
            self.capture_thread = None
        with self.capture_mutex:
            if self.capture is not None:
                self.capture.release()
                self.capture = None

    def get_frame_jpg(self):
        """Returns the latest frame captured by the camera as JPG"""
        ts = time.time() * 1000
        frame = self._frame
        if frame is None:
            return None, 0, 0, ts
        height, width = frame[0].shape[:2]
        jpg, w, h = convert_frame(frame[0], width, height, self.scaling, self.quality)
        return jpg, w, h, ts

    def _run(self):
        """Thread to grab the most recent frame, decoding at the publish rate

        Only the capture thread touches ``self.capture``, so the grab loop does
        not hold ``capture_mutex``: holding it across every grab starved
        ``get_frame_jpg()``, which could then wait seconds for a frame that was
        already decoded.
        """
        failures = 0
        next_retrieve = 0.0
        while self.running:
            try:
                # Try to grab always the latest frame
                grabbed = self.capture is not None and self.capture.grab()
            except Exception as e:
                self.logger.error(f"Failed to grab video frame {e}")
                grabbed = False
            if grabbed:
                if failures:
                    self.logger.info(
                        f"Video stream recovered after {failures} failed grabs"
                    )
                    failures = 0
                now = time.monotonic()
                if now < next_retrieve:
                    continue
                try:
                    retrieved, frame = self.capture.retrieve()
                except Exception as e:
                    self.logger.error(f"Failed to decode video frame {e}")
                    retrieved = False
                if retrieved:
                    self._frame = (frame, now)
                    next_retrieve = now + self._retrieve_interval
                continue
            # A grab against a dead stream fails immediately, so without a
            # reopen this loop spins at 100% of a core for as long as the stream
            # stays down -- and video never comes back, because nothing rebuilds
            # the capture.
            failures += 1
            self._reopen(failures)

    def _reopen(self, failures):
        """Release and rebuild the capture, backing off first"""
        if failures == 1:
            self.logger.warning(
                "Video stream unavailable; reopening with backoff up to "
                f"{self.REOPEN_BACKOFF_SECONDS[-1]:.0f}s"
            )
        with self.capture_mutex:
            if self.capture is not None:
                self.capture.release()
                self.capture = None
        index = min(failures, len(self.REOPEN_BACKOFF_SECONDS)) - 1
        if self._closing.wait(self.REOPEN_BACKOFF_SECONDS[index]) or not self.running:
            return
        try:
            capture = self._open_capture()
        except Exception as e:
            self.logger.error(f"Failed to reopen video stream {e}")
            return
        with self.capture_mutex:
            self.capture = capture


class CameraStreamer:
    """Streams video from a camera to InOrbit.

    A single long-lived worker thread owns the camera lifecycle. ``start``,
    ``stop`` and ``shutdown`` only toggle threading Events, so they never block
    the caller -- in particular the MQTT callback thread that dispatches module
    load/unload, where a blocking call would starve the keepalive and drop the
    connection. Opening/closing the camera (which can block while a stream is
    unreachable) happens entirely on the worker thread.

    Because there is exactly one worker, ``camera.open()`` and ``camera.close()``
    are always serialized -- the device is never opened and closed concurrently,
    which removes the start/stop races of a spawn-per-start model.
    """

    # Backoff after a failed streaming session so a permanently-broken URL does
    # not hot-loop open->fail->open. A pending stop/shutdown short-circuits it.
    BACKOFF_SECONDS = 1.0

    def __init__(self, camera, publish_frame_callback):
        self.logger = logging.getLogger(__class__.__name__)
        self.camera = camera
        self.publish_frame = publish_frame_callback
        # Set => the worker should be streaming. Cleared => paused.
        self._streaming = threading.Event()
        # Set => the worker should exit permanently.
        self._shutdown = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def start(self):
        """Request streaming. Non-blocking; safe to call repeatedly."""
        self._streaming.set()

    def stop(self):
        """Pause streaming. Non-blocking; safe to call repeatedly.

        The worker thread stays alive and idle, ready for a later ``start()``.
        Use ``shutdown()`` to terminate the worker permanently.
        """
        self._streaming.clear()

    def shutdown(self):
        """Permanently stop the worker. Non-blocking.

        ``_shutdown`` is set before ``_streaming`` so a worker waking from the
        idle wait observes the shutdown rather than starting a doomed session.
        """
        self._shutdown.set()
        self._streaming.set()

    def join(self, timeout=None):
        """Wait for the worker thread to exit (after ``shutdown()``)."""
        self._worker.join(timeout)

    def is_alive(self):
        """Return True while the worker thread is running."""
        return self._worker.is_alive()

    def _run(self):
        """Worker loop: idle until streaming is requested, then grab frames from
        the camera at the desired rate and publish them until paused or shut down.

        The per-session body is wrapped so a failed ``open()``/``get_frame_jpg()``
        cannot kill the long-lived worker -- it logs, backs off, and waits for the
        next ``start()``.
        """
        while not self._shutdown.is_set():
            # Idle until streaming or shutdown is requested.
            self._streaming.wait()
            if self._shutdown.is_set():
                break
            try:
                self.camera.open()
                while self._streaming.is_set() and not self._shutdown.is_set():
                    jpg, width, height, ts = self.camera.get_frame_jpg()
                    if jpg is not None:
                        self.publish_frame(jpg, width, height, ts)
                    time.sleep(1.0 / self.camera.rate)
            except Exception:
                self.logger.exception("Camera streaming session failed")
                # Back off so a permanently-failing open does not hot-loop while
                # streaming is still requested.
                self._shutdown.wait(timeout=self.BACKOFF_SECONDS)
            finally:
                try:
                    self.camera.close()
                except Exception:
                    self.logger.exception("Error closing camera")
