#!/usr/bin/env python
# -*- coding: utf-8 -*-

# IMPORTANT: this file will be removed. Only used during initial development phase.

import logging
from time import sleep
from inorbit_edge.robot import RobotSession

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("debug.log"), logging.StreamHandler()],
)

log = logging.getLogger(__name__)

robot_session = RobotSession(
    robot_id="edgesdk_python_robot_2",
    robot_name="edgesdk_python_robot",
    api_key="dM2hJtKebPYJmbgz",
    use_ssl=False,
)

robot_session.connect()

robot_session.publish_pose(0, 0, 0)
sleep(1)
robot_session.publish_pose(0, 0, 1)
sleep(1)
robot_session.publish_pose(0, 0, 2)
sleep(1)
robot_session.publish_pose(0, 0, 3)
sleep(1)
robot_session.publish_pose(0, 0, 4)
sleep(20)
log.info(robot_session)
robot_session.publish_key_values({"k1": "1", "k2": "my_value"})
sleep(10)
robot_session.disconnect()
