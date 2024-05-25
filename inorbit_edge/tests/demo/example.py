#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from time import sleep
from random import randint, uniform, random
from math import pi
import os
import sys
from math import inf

from inorbit_edge.robot import RobotSessionFactory, RobotSessionPool, LaserConfig
from inorbit_edge.video import OpenCVCamera

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


if __name__ == "__main__":
    inorbit_api_endpoint = os.environ.get("INORBIT_URL")
    inorbit_api_url = os.environ.get("INORBIT_API_URL")
    inorbit_api_use_ssl = os.environ.get("INORBIT_USE_SSL")
    inorbit_api_key = os.environ.get("INORBIT_API_KEY")

    # For InOrbit Connect (https://connect.inorbit.ai/) certified robots,
    # use a yaml file to define the robot_key for each robot_id. This
    # file stores additional params such as robot_name, etc.
    inorbit_robots_config = os.environ.get("INORBIT_ROBOT_CONFIG_FILE")

    # If configured stream video as if it was a robot camera
    video_url = os.environ.get("INORBIT_VIDEO_URL")

    assert inorbit_api_endpoint, "Environment variable INORBIT_URL not specified"
    assert inorbit_api_url, "Environment variable INORBIT_API_URL not specified"
    assert inorbit_api_key, "Environment variable INORBIT_API_KEY not specified"

    # Create robot session factory and session pool
    robot_session_factory = RobotSessionFactory(
        endpoint=inorbit_api_endpoint,
        api_key=inorbit_api_key,
        use_ssl=inorbit_api_use_ssl == "true",
    )
    robot_session_factory.register_command_callback(log_command)
    robot_session_factory.register_command_callback(my_command_handler)
    robot_session_factory.register_commands_path("./user_scripts", r".*\.sh")

    robot_session_pool = RobotSessionPool(robot_session_factory, inorbit_robots_config)
    # Dictionary mapping robot ID and fake robot object
    fake_robot_pool = dict()

    # Create fake robots and populate `fake_robot_pool` dictionary
    for i in range(NUM_ROBOTS):
        cur_robot_id = "edgesdk_py_{}".format(i)
        robot_session = robot_session_pool.get_session(
            robot_id=cur_robot_id, robot_name=cur_robot_id
        )
        fake_robot_pool[cur_robot_id] = FakeRobot(
            robot_id=cur_robot_id, robot_name=cur_robot_id
        )
        img = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map.png")
        robot_session.publish_map(img, "map", "map", -1.5, -1.5, 0.05)
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
                ranges, angles = [], []
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
