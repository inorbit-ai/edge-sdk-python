#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from time import sleep
from random import randint, uniform, random
from math import pi
import os
import requests

from inorbit_edge.robot import RobotSessionFactory, RobotSessionPool

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)


MAX_X = 20
MAX_Y = 20
MAX_YAW = 2 * pi

NUM_ROBOTS_LOCATION = 1


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
        self.network=0
        self.disk_usage=0
        self.status = "Idle"

        # robot basic data
        self.manufacturer="Hooli Robotics"
        self.version="1.0"
        self.model= robot_id + "_1.0.11"

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


        # Generate a random integer value for battery
        self.battery = randint(0, 100)
        # Generate random status
        self.status = "Mission" if random() > 0.5 else "Idle"
        # Generate a random float value for cpu usage
        self.cpu = random() * 100
        # Generate a random int value for network
        self.network = randint(0, 50)
        # Generate a random int value for disk usage
        self.disk_usage = randint(0, 200)

        self.logger.debug(
            "New position x={}, y={}, yaw={}".format(self.x, self.y, self.yaw)
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
    )
    robot_session_pool = RobotSessionPool(robot_session_factory)

    # Dictionary mapping robot ID and fake robot object
    fake_robot_pool = dict()

    # Create fake robots and populate `fake_robot_pool` dictionary
    for i in range(NUM_ROBOTS_LOCATION):
        robot_id = "Seth"
        #robot_id = "edgesdk_py_loc1_{}".format(i)
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

    for i in range(NUM_ROBOTS_LOCATION):
        robot_id= "Venus"
        #robot_id = "edgesdk_py_loc2_{}".format(i)
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
                    "network": fake_robot.network,
                    "disk_usage": fake_robot.disk_usage,
                    "manufacturer": fake_robot.manufacturer,
                    "version": fake_robot.version,
                    "model": fake_robot.model
                }
            )

        sleep(1)
