#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from time import sleep
from random import randint, uniform, random
from math import pi
import os
import requests
import sys

from inorbit_edge.robot import RobotSessionFactory, RobotSessionPool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)


MAX_X = 20
MAX_Y = 20
MAX_YAW = 2 * pi

NUM_ROBOTS = 2


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
            self.yaw = self.yaw - yaw_delta

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


def my_custom_command_handler(robot_session, message):
    """Callback for custom actions.

    Callback method executed for messages published on the ``custom_command``
    topic. It recieves the RobotSession object and the message that contains
    the ``cmd`` and ``ts`` fields.

    Args:
        robot_session (RobotSession): RobotSession object
        message (dict): Message with the ``cmd`` string as defined
            on InOrbit Custom Defined action and ``ts``.
    """

    print(
        "Robot '{}' received command '{}'".format(
            robot_session.robot_id, message["cmd"]
        )
    )


if __name__ == "__main__":

    inorbit_api_endpoint = os.environ.get("INORBIT_URL")
    inorbit_api_url = os.environ.get("INORBIT_API_URL")
    inorbit_api_key = os.environ.get("INORBIT_API_KEY")
    inorbit_api_use_ssl = os.environ.get("INORBIT_API_USE_SSL")

    assert inorbit_api_endpoint, "Environment variable INORBIT_URL not specified"
    assert inorbit_api_url, "Environment variable INORBIT_API_URL not specified"
    assert inorbit_api_key, "Environment variable INORBIT_API_KEY not specified"

    # Create robot session factory and session pool
    robot_session_factory = RobotSessionFactory(
        endpoint=inorbit_api_endpoint,
        api_key=inorbit_api_key,
        use_ssl=False if inorbit_api_use_ssl == "false" else True,
        custom_command_callback=my_custom_command_handler,
    )
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
                        (fake_robot.x + 20, fake_robot.y + 10)
                    ]
                )

            sleep(1)
        except KeyboardInterrupt:
            robot_session_pool.tear_down()
            sys.exit()
