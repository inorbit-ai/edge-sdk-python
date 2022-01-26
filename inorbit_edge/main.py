#!/usr/bin/env python
# -*- coding: utf-8 -*-

# IMPORTANT: this file will be removed. Only used during initial development phase.

import logging
from inorbit_edge.robot import RobotSession

# from time import sleep

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("debug.log"), logging.StreamHandler()],
)

log = logging.getLogger(__name__)

robot_session = RobotSession(
    robot_id="edgesdk_python_robot",
    robot_name="edgesdk_python_robot",
    app_key="t7WbNVmRZxVZSxcZ",
    endpoint="http://localdev.com:3000/cloud_sdk_robot_config",
    use_ssl=False,
)

robot_session.connect()

# sleep(10)

robot_session.disconnect()
