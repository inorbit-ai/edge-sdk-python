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
    """Camera implementation backed up by OpenCV"""

    def __init__(self, video_url, rate=10, scaling=0.3, quality=35):
        self.video_url = video_url
        self.capture = None
        self.capture_mutex = threading.Lock()
        self.running = False
        self.logger = logging.getLogger(__class__.__name__)
        self.rate = rate
        self.scaling = scaling
        self.quality = quality

    def open(self):
        """Opens the capturing device / stream"""
        with self.capture_mutex:
            if self.capture is None:
                self.capture = cv2.VideoCapture(self.video_url)
            if not self.running:
                self.running = True
                threading.Thread(target=self._run).start()

    def close(self):
        """Closes the capturing device / stream"""
        with self.capture_mutex:
            if self.capture is not None:
                self.capture.release()
                self.capture = None
            self.running = False

    def get_frame_jpg(self):
        """Returns the latest frame captured by the camera as JPG"""
        ts = time.time() * 1000
        with self.capture_mutex:
            # decode the latest grabbed frame
            ret, frame = self.capture.retrieve()
            if not ret:
                return None, 0, 0, ts
            width = self.capture.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
            jpg, w, h = convert_frame(frame, width, height, self.scaling, self.quality)
            return jpg, w, h, ts

    def _run(self):
        """Thread to grab always the most recent frame"""
        while self.running:
            with self.capture_mutex:
                try:
                    # Try to grab always the latest frame
                    self.capture.grab()
                except Exception as e:
                    self.logger.error(f"Failed to grab video frame {e}")


class CameraStreamer:
    """Streams video from a camera to InOrbit"""

    def __init__(self, camera, publish_frame_callback):
        self.camera = camera
        self.running = False
        self.mutex = threading.Lock()
        self.publish_frame = publish_frame_callback
        self.must_stop = False

    def start(self):
        """Streams video to the platform"""
        with self.mutex:
            self.must_stop = False
            if not self.running:
                self.running = True
                threading.Thread(target=self._run).start()

    def stop(self):
        """Stops streaming video to the platform"""
        self.must_stop = True

    def _run(self):
        """This thread takes care of getting video from a camera at the desired rate,
        converting it to the right format and publishing the video frames"""
        self.camera.open()
        while True:
            jpg, width, height, ts = self.camera.get_frame_jpg()
            if jpg is not None:
                self.publish_frame(jpg, width, height, ts)
            time.sleep(1.0 / self.camera.rate)
            with self.mutex:
                if self.must_stop:
                    break
        self.camera.close()
        self.running = False
