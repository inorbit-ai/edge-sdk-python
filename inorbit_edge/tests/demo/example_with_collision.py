#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import datetime
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

MAX_X = 13
MAX_Y = 14.5
MAX_YAW = 2 * pi

NUM_ROBOTS_LOCATION = 2


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
    """Class that simulates robot data and generates new poses"""

    def __init__(self, robot_id, robot_name) -> None:
        self.logger = logging.getLogger(__class__.__name__)
        self.robot_id = robot_id
        self.robot_name = robot_name

        # Set initial x, y position and yaw
        if(robot_id == "mars"):
            self.x = 8
            self.y = 10
            self.yaw = -5.2
        if(robot_id == "moon"):
            self.x = 2
            self.y = 15
            self.yaw = -6.3
        # Initialize other robot data
        self.cpu = 0
        self.battery = 0
        self.status = "Idle"
        self.collide = 0
        # # Initialize odometry data
        # self.linear_distance = 0
        # self.angular_distance = 0
        # self.linear_speed = 0
        # self.angular_speed = 0

    def move(self):
        """Modifies robot data using values"""
        if(robot_id == "mars"):
            x_delta = 0.25
            y_delta = 0.25
            yaw_delta = 1
        if(robot_id == "moon"):
            x_delta = 0.53
            y_delta = 0
            yaw_delta = 1

        # Ignore position update if the new coordinate exceeds x limits
        if self.x + x_delta < MAX_X and self.x + x_delta > 0:
            self.x = self.x + x_delta
        else:
            self.collide = 1

        # Ignore position update if the new coordinate exceeds y limits
        if self.y + y_delta < MAX_Y and self.y + y_delta > 0:
            self.y = self.y + y_delta

        # Ignore orientation update if the new yaw exceeds yaw limits
        if self.yaw + yaw_delta < MAX_YAW and self.yaw + yaw_delta > 0:
            self.yaw = self.yaw + yaw_delta

        # Generate a random integer value for battery
        self.battery = randint(0, 100)
        # Generate random status
        self.status = "Mission" if random() > 0.5 else "Idle"
        # Generate a random float value for cpu usage
        self.cpu = random() * 100
        self.demo_robot = 'demo_robot'

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
        use_ssl=False if inorbit_api_use_ssl == "false" else True
    )
    robot_session_pool = RobotSessionPool(robot_session_factory)

    # Dictionary mapping robot ID and fake robot object
    fake_robot_pool = dict()
    i = 0
    # Create 2 fake robots and populate `fake_robot_pool` dictionary
    for i in range(NUM_ROBOTS_LOCATION):
        if (i == 0):
            robot_id = "mars"
        else:
            robot_id = "moon"
        robot_session = robot_session_pool.get_session(
            robot_id=robot_id, robot_name=robot_id.capitalize()
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
    i = 0
    # Go through both fake robots and simulate robot movement until they are about to collide
    while (i == 0):
        for robot_id, fake_robot in fake_robot_pool.items():
                fake_robot.move()
                robot_session = robot_session_pool.get_session(robot_id=robot_id)
                
                robot_session.publish_pose(
                    x=fake_robot.x, y=fake_robot.y, yaw=fake_robot.yaw
                )
                robot_session.publish_key_values(
                    {
                        "battery": fake_robot.battery,
                        "status": fake_robot.status,
                        "cpu": fake_robot.cpu,
                        "collide": fake_robot.collide,
                        "demo_robot": fake_robot.demo_robot
                    }
                )
        sleep(1)
