#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
import socket
import sys
from time import sleep
from random import randint, uniform, random
from math import pi, inf

from inorbit_edge.metrics import setup_prometheus_meter_provider
from inorbit_edge.robot import (
    RobotSessionFactory,
    RobotSessionPool,
    LaserConfig,
    RobotFootprintSpec,
)
from inorbit_edge.video import OpenCVCamera

try:
    from prometheus_client import start_http_server
except ImportError:
    start_http_server = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)

MAX_X = 20
MAX_Y = 20
MAX_YAW = 2 * pi

LIDAR_RANGES = 700
LIDAR_MIN = 2.0
LIDAR_MAX = 3.2

NUM_ROBOTS = 2
NUM_LASERS = 3


def _mqtt_use_ssl():
    """Use TLS for MQTT unless INORBIT_USE_SSL is false, 0, no, or off."""
    v = os.environ.get("INORBIT_USE_SSL", "true").strip().lower()
    return v not in ("false", "0", "no", "off")


def _required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


class FakeRobot:
    """Class that simulates robot data and generates random data"""

    def __init__(self, robot_id, robot_name) -> None:
        self.logger = logging.getLogger(__class__.__name__)
        self.robot_id = robot_id
        self.robot_name = robot_name

        # Set initial x, y position and yaw
        self.x = uniform(-MAX_X / 4, MAX_X / 4)
        self.y = uniform(-MAX_Y / 4, MAX_Y / 4)
        self.yaw = uniform(0, MAX_YAW / 2)
        self.frame_id = "map"

        # Initialize other robot data
        self.cpu = 0
        self.battery = 0
        self.status = "Idle"

        # Initialize odometry data
        self.linear_distance = 0
        self.angular_distance = 0
        self.linear_speed = 0
        self.angular_speed = 0

    def move(self):
        """Modifies robot data using values generated randomly"""

        # Generate random deltas for x, y and yaw
        x_delta = uniform(-2, 2)
        y_delta = uniform(-2, 2)
        yaw_delta = uniform(-pi / 2, pi / 2)

        # Ignore position update if the new coordinate exceeds x limits
        if MAX_X > self.x + x_delta > 0:
            self.x = self.x + x_delta

        # Ignore position update if the new coordinate exceeds y limits
        if MAX_Y > self.y + y_delta > 0:
            self.y = self.y + y_delta

        # Ignore orientation update if the new yaw exceeds yaw limits
        if MAX_YAW > self.yaw + yaw_delta > 0:
            self.yaw = self.yaw + yaw_delta

        self.linear_distance = random() * 10
        self.angular_distance = random() * 2
        self.linear_speed = uniform(-1, 1)
        self.angular_speed = uniform(-pi / 4, pi / 4)

        # Generate a random integer value for battery
        self.battery = randint(0, 100)
        # Generate random status
        self.status = "Mission" if random() > 0.5 else "Idle"
        # Generate a random float value for cpu usage
        self.cpu = random() * 100


def log_command(robot_id, command_name, args, options):
    """Callback for printing command execution.

    Args:
        robot_id (str): InOrbit robot ID
        command_name (str): InOrbit command e.g. 'customCommand'
        args (list): Command arguments
        options (dict): object that includes
            - `result_function` can be called to report command execution result. It
            has the following signature: `result_function(return_code)`.
            - `progress_function` can be used to report command output and has the
            following signature: `progress_function(output, error)`.
            - `metadata` is reserved for the future and will contain additional
            information about the received command request.
    """

    print("Received command! What should I do now?")
    print(robot_id, command_name, args, options)


def my_command_handler(robot_id, command_name, args, options):
    """Handler for processing custom command calls.

    Args:
        robot_id (str): InOrbit robot ID
        command_name (str): InOrbit command e.g. 'customCommand'
        args (list): Command arguments
        options (dict): object that includes
            - `result_function` can be called to report command execution result. It
            has the following signature: `result_function(return_code)`.
            - `progress_function` can be used to report command output and has the
            following signature: `progress_function(output, error)`.
            - `metadata` is reserved for the future and will contain additional
            information about the received command request.
    """
    if command_name == "customCommand":
        print(f"Received '{command_name}' for robot '{robot_id}'!. {args}")
        # Return '0' for success
        options["result_function"]("0")


def _init_prometheus_metrics():
    """Serve /metrics when INORBIT_METRICS_PORT is set (pip extra telemetry)."""
    port_s = os.environ.get("INORBIT_METRICS_PORT", "").strip()
    if not port_s:
        return
    try:
        port = int(port_s)
    except ValueError:
        logging.warning("INORBIT_METRICS_PORT is not a valid integer: %r", port_s)
        return
    if port <= 0:
        return

    service_name = os.environ.get(
        "INORBIT_METRICS_SERVICE_NAME", "inorbit-edge-sdk-demo"
    )
    if (
        not setup_prometheus_meter_provider(
            service_name=service_name,
            service_instance_id=socket.gethostname(),
        )
        or start_http_server is None
    ):
        logging.warning(
            "INORBIT_METRICS_PORT=%s set but telemetry packages missing. "
            "Use: pip install 'inorbit-edge[telemetry]'",
            port_s,
        )
        return

    host = os.environ.get("INORBIT_METRICS_ADDR", "0.0.0.0")
    start_http_server(port=port, addr=host)
    logging.info(
        "OpenTelemetry metrics (Prometheus) on http://%s:%s/metrics",
        host,
        port,
    )


def main():
    _init_prometheus_metrics()

    robot_footprint = RobotFootprintSpec(
        footprint=[
            {"x": -0.5, "y": -0.5},
            {"x": 0.3, "y": -0.5},
            {"x": 0.7, "y": 0.0},
            {"x": 0.3, "y": 0.5},
            {"x": -0.5, "y": 0.5},
        ],
        radius=0.2,
    )

    inorbit_api_endpoint = _required_env("INORBIT_URL")
    inorbit_api_url = _required_env("INORBIT_API_URL")
    inorbit_account_id = _required_env("INORBIT_ACCOUNT_ID")
    inorbit_api_key = _required_env("INORBIT_API_KEY")

    # If configured stream video as if it was a robot camera
    video_url = os.environ.get("INORBIT_VIDEO_URL")

    # Robot ids are always "<prefix>_edgesdk_demo_<n>". Prefix is mandatory.
    robot_id_prefix = _required_env("INORBIT_ROBOT_ID_PREFIX")
    logging.info("Robot id prefix: %r", robot_id_prefix)

    # Create robot session factory and session pool
    robot_session_factory = RobotSessionFactory(
        endpoint=inorbit_api_endpoint,
        rest_api_endpoint=inorbit_api_url,
        api_key=inorbit_api_key,
        use_ssl=_mqtt_use_ssl(),
        account_id=inorbit_account_id,
    )
    robot_session_factory.register_command_callback(log_command)
    robot_session_factory.register_command_callback(my_command_handler)
    robot_session_factory.register_commands_path("./user_scripts", r".*\.sh")

    robot_session_pool = RobotSessionPool(robot_session_factory)
    # Dictionary mapping robot ID and fake robot object
    fake_robot_pool = dict()

    # Create fake robots and populate `fake_robot_pool` dictionary
    for i in range(NUM_ROBOTS):
        cur_robot_id = "{}_edgesdk_demo_{}".format(robot_id_prefix, i)
        robot_session = robot_session_pool.get_session(
            robot_id=cur_robot_id, robot_name=cur_robot_id
        )
        fake_robot_pool[cur_robot_id] = FakeRobot(
            robot_id=cur_robot_id, robot_name=cur_robot_id
        )
        img = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map.png")
        robot_session.publish_map(
            file=img,
            map_id="my_map",
            map_label="Testing facilities",
            frame_id="map",
            x=-1.5,
            y=-1.5,
            resolution=0.05,
        )
        if video_url is not None:
            robot_session.register_camera("0", OpenCVCamera(video_url))

        # Configure lasers
        configs = []
        for j in range(NUM_LASERS):
            configs.append(
                LaserConfig(
                    j * random(),
                    j * random(),
                    pi * j * random(),
                    (-pi / (j + 1), pi / (j + 1)),
                    (LIDAR_MIN, LIDAR_MAX),
                    LIDAR_RANGES,
                )
            )
        robot_session.register_lasers(configs)

        # Configure robot footprint
        if robot_footprint:
            robot_session.apply_footprint(robot_footprint)

    # Go through every fake robot and simulate robot movement
    while True:
        try:
            for cur_robot_id, fake_robot in fake_robot_pool.items():
                fake_robot.move()

                # Get the corresponding robot session and publish robot data
                robot_session = robot_session_pool.get_session(robot_id=cur_robot_id)
                robot_session.publish_pose(
                    x=fake_robot.x,
                    y=fake_robot.y,
                    yaw=fake_robot.yaw,
                    frame_id=fake_robot.frame_id,
                )
                robot_session.publish_system_stats(cpu_load_percentage=random())
                robot_session.publish_key_values(
                    {
                        "battery": fake_robot.battery,
                        "status": fake_robot.status,
                    }
                )
                robot_session.publish_key_values(
                    {
                        "foo": "bar",
                    }
                )
                robot_session.publish_odometry(
                    linear_distance=fake_robot.linear_distance,
                    angular_distance=fake_robot.angular_distance,
                    linear_speed=fake_robot.linear_speed,
                    angular_speed=fake_robot.angular_speed,
                )

                robot_session.publish_path(
                    path_points=[
                        (fake_robot.x, fake_robot.y),
                        (fake_robot.x + 10, fake_robot.y + 10),
                        (fake_robot.x + 20, fake_robot.y + 10),
                    ]
                )

                # Publish multiple lasers
                ranges = []
                for i in range(NUM_LASERS):
                    # Generate random lidar ranges within arbitrary limits
                    lidar = [max(LIDAR_MIN, random() * LIDAR_MAX) for _ in range(700)]
                    # Make ranges over threshold infinite
                    lidar = [inf if r >= 3 else r for r in lidar]
                    ranges.append(lidar)
                # NOTE: for publishing laser scans the robot pose is needed.
                # In that case, avoid using publish_pose method.
                robot_session.publish_lasers(
                    x=fake_robot.x,
                    y=fake_robot.y,
                    yaw=fake_robot.yaw,
                    ranges=ranges,
                )

            sleep(1)
        except KeyboardInterrupt:
            robot_session_pool.tear_down()
            sys.exit()


if __name__ == "__main__":
    main()
