#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from time import sleep
from random import randint, uniform, random
from math import pi
import os
import requests
import sys
from math import inf

from inorbit_edge.robot import RobotSessionFactory, RobotSessionPool
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

NUM_ROBOTS = 1


# TODO: integrate this into the Edge SDK ``RobotSession`` class
def publish_robot_map(inorbit_api_url, inorbit_api_key, robot_id, map_file):
    url = inorbit_api_url + "/robots/" + robot_id + "/maps"

    payload = {
        "metadata": '{"mapId":"map", "label": "map", "resolution": 0.1, "x": -15, "y": -15}'  # noqa: E501
    }
    files = [
        (
            "image",
            ("map.png", open(map_file, "rb"), "image/png"),
        )
    ]
    headers = {"x-auth-inorbit-app-key": inorbit_api_key}

    requests.request("POST", url, headers=headers, data=payload, files=files)


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
        if self.x + x_delta < MAX_X and self.x + x_delta > 0:
            self.x = self.x + x_delta

        # Ignore position update if the new coordinate exceeds y limits
        if self.y + y_delta < MAX_Y and self.y + y_delta > 0:
            self.y = self.y + y_delta

        # Ignore orientation update if the new yaw exceeds yaw limits
        if self.yaw + yaw_delta < MAX_YAW and self.yaw + yaw_delta > 0:
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
            - `metadata` is reserved for the future and will contains additional
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
            - `metadata` is reserved for the future and will contains additional
            information about the received command request.
    """
    if command_name == "customCommand":
        print(f"Received '{command_name}' for robot '{robot_id}'!. {args}")
        # Return '0' for success
        options["result_function"]("0")


if __name__ == "__main__":
    inorbit_api_endpoint = os.environ.get("INORBIT_URL")
    inorbit_api_url = os.environ.get("INORBIT_API_URL")
    inorbit_api_use_ssl = os.environ.get("INORBIT_API_USE_SSL")
    inorbit_api_key = os.environ.get("INORBIT_API_KEY")
    inorbit_robot_key = os.environ.get("INORBIT_ROBOT_KEY")

    # If configured stream video as if it was a robot camera
    video_url = os.environ.get("INORBIT_VIDEO_URL")

    assert inorbit_api_endpoint, "Environment variable INORBIT_URL not specified"
    assert inorbit_api_url, "Environment variable INORBIT_API_URL not specified"
    assert inorbit_api_key, "Environment variable INORBIT_API_KEY not specified"

    # Create robot session factory and session pool
    # If a robot_key is specified, use it as for authentication. Otherwise, use
    # the api_key.
    if inorbit_robot_key:        
        robot_session_factory = RobotSessionFactory(
            endpoint=inorbit_api_endpoint,
            robot_key=inorbit_robot_key,
            use_ssl=False if inorbit_api_use_ssl == "false" else True,
        )
    else:
        # Create robot session factory and session pool
        robot_session_factory = RobotSessionFactory(
            endpoint=inorbit_api_endpoint,
            api_key=inorbit_api_key,
            use_ssl=False if inorbit_api_use_ssl == "false" else True,
        )
    robot_session_factory.register_command_callback(log_command)
    robot_session_factory.register_command_callback(my_command_handler)
    robot_session_factory.register_commands_path("./user_scripts", r".*\.sh")

    robot_session_pool = RobotSessionPool(robot_session_factory)
    # Dictionary mapping robot ID and fake robot object
    fake_robot_pool = dict()

    # Create fake robots and populate `fake_robot_pool` dictionary
    for i in range(NUM_ROBOTS):
        robot_id = "edgesdk_py_{}".format(i)
        robot_session = robot_session_pool.get_session(
            robot_id=robot_id, robot_name=robot_id
        )
        fake_robot_pool[robot_id] = FakeRobot(robot_id=robot_id, robot_name=robot_id)
        publish_robot_map(
            inorbit_api_url=inorbit_api_url,
            inorbit_api_key=inorbit_api_key,
            robot_id=robot_id,
            map_file=os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "map.png"
            ),
        )
        if video_url is not None:
            robot_session.register_camera("0", OpenCVCamera(video_url))

    # Go through every fake robot and simulate robot movement
    while True:
        try:
            for robot_id, fake_robot in fake_robot_pool.items():
                fake_robot.move()

                # Get the corresponding robot session and publish robot data
                robot_session = robot_session_pool.get_session(robot_id=robot_id)
                robot_session.publish_pose(
                    x=fake_robot.x, y=fake_robot.y, yaw=fake_robot.yaw
                )
                robot_session.publish_key_values(
                    {
                        "battery": fake_robot.battery,
                        "status": fake_robot.status,
                        "cpu": fake_robot.cpu,
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

                # Generate random lidar ranges within arbitrary limits
                lidar = [max(2, random() * 3.2) for _ in range(LIDAR_RANGES)]
                # Make ranges over threshold infinite
                lidar = [inf if r >= 3 else r for r in lidar]
                robot_session.publish_laser(
                    x=fake_robot.x,
                    y=fake_robot.y,
                    yaw=fake_robot.yaw,
                    ranges=lidar,
                    angle=(-pi / 3, pi / 3),  # show lidar ranges on a cone
                )

            sleep(1)
        except KeyboardInterrupt:
            robot_session_pool.tear_down()
            sys.exit()
