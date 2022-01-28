#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from time import sleep
from random import uniform
from math import pi
from inorbit_edge import robot

from inorbit_edge.robot import RobotSessionFactory, RobotSessionPool

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("debug.log"), logging.StreamHandler()],
)

log = logging.getLogger(__name__)


MAX_X = 20
MAX_Y = 20
MAX_YAW = 2*pi

class FakeRobot:
    def __init__(self, robot_id, robot_name) -> None:
        self.logger = logging.getLogger(__class__.__name__)
        self.robot_id = robot_id
        self.robot_name = robot_name

        self.x = uniform(-MAX_X/4, MAX_X/4)
        self.y = uniform(-MAX_Y/4, MAX_Y/4)

        self.yaw = uniform(0, MAX_YAW/2)
    
    def move(self):
        x_delta = uniform(-2, 2)
        y_delta = uniform(-2, 2)
        yaw_delta = uniform(-pi/2, pi/2)

        if self.x + x_delta < MAX_X and self.x + x_delta > 0:
            self.x = self.x + x_delta

        if self.y + y_delta < MAX_Y and self.y + y_delta > 0:
            self.y = self.y + y_delta

        if self.yaw + yaw_delta < MAX_YAW and self.yaw + yaw_delta > 0:
            self.yaw = self.yaw - yaw_delta

        self.logger.debug("New position x={}, y={}, yaw={}".format(self.x, self.y, self.yaw))

robot_session_factory = RobotSessionFactory(
    endpoint="http://localdev.com:3000/cloud_sdk_robot_config",
    api_key="dM2hJtKebPYJmbgz",
    use_ssl=False
)

robot_session_pool = RobotSessionPool(robot_session_factory)

fake_robot_pool = dict()

for i in range(10):
    robot_id = "edgesdk_py_loc1_{}".format(i)
    log.info("Creating robot session for '{}'".format(robot_id))
    robot_session = robot_session_pool.get_session(robot_id=robot_id, robot_name=robot_id)
    fake_robot_pool[robot_id] = FakeRobot(robot_id=robot_id, robot_name=robot_id)

    robot_id = "edgesdk_py_loc2_{}".format(i)
    log.info("Creating robot session for '{}'".format(robot_id))
    robot_session = robot_session_pool.get_session(robot_id=robot_id, robot_name=robot_id)
    fake_robot_pool[robot_id] = FakeRobot(robot_id=robot_id, robot_name=robot_id)


while True:
    for robot_id, fake_robot in fake_robot_pool.items():
        fake_robot.move()
        robot_session = robot_session_pool.get_session(robot_id=robot_id)
        robot_session.publish_pose(x=fake_robot.x, y=fake_robot.y, yaw=fake_robot.yaw)

    sleep(1)