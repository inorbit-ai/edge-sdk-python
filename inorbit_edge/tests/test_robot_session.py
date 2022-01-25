#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytest
from inorbit_edge.robot import RobotSession


@pytest.mark.parametrize(
    "robot_id, robot_name, app_key",
    [
        # (robot_id, robot_name, app_key)
        ("abc123", "R2D2", "s3cr3t")
    ],
)
def test_foo(robot_id, robot_name, app_key):
    robot_session = RobotSession(robot_id, robot_name, app_key)
    assert robot_session.robot_id == robot_id
    assert robot_session.robot_name == robot_name
    assert robot_session.app_key == app_key
