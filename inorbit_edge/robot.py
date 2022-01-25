#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from typing import Any, Tuple
from inorbit_edge import __version__ as inorbit_edge_version

class RobotSession:
    def __init__(self, robot_id, robot_name, app_key, **kwargs) -> None:
        """Initialize a robot session.

        Args:
            robot_id (str): ID of the robot
            robot_name (str): Robot name
            agent_version (str): Agent Version
            app_key (str): Application key for authenticating against InOrbit
            endpoint ([type]): InOrbit URL
        """

        self.robot_id = robot_id
        self.robot_name = robot_name
        self.app_key = app_key
        self.agent_version = f"{inorbit_edge_version}.edgesdk_py"
        self.endpoint = kwargs.get("endpoint", "https://control.inorbit.ai/cloud_sdk_robot_config")


    def _fetch_robot_config(self):
        raise NotImplementedError()

    def connect(self):
        raise NotImplementedError()

    def publish(self, topic, message, options):
        raise NotImplementedError()