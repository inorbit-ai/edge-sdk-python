#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import unittest.mock
from inorbit_edge.robot import RobotSession
from inorbit_edge.inorbit_pb2 import OdometryDataMessage


def test_odometry_accumulation(mock_mqtt_client, mock_inorbit_api, mock_sleep):
    """RobotSession should accumulate angular and linear distance based on the
    published poses and publish them if values for them are not explicitly provided"""

    with unittest.mock.patch("time.time", return_value=1):
        robot_session = RobotSession(
            robot_id="id_123",
            robot_name="name_123",
            api_key="apikey_123",
        )

    # Disable throttling for testing
    robot_session._publish_throttling["publish_pose"]["min_time_between_calls"] = 0
    robot_session._publish_throttling["publish_odometry"]["min_time_between_calls"] = 0

    # Initial state should be 0
    assert robot_session._odometry_accumulator_linear == 0.0
    assert robot_session._odometry_accumulator_angular == 0.0

    # Publish first pose (no distance accumulated yet)
    robot_session.publish_pose(x=0, y=0, yaw=0)
    assert robot_session._odometry_accumulator_linear == 0.0
    assert robot_session._odometry_accumulator_angular == 0.0

    # Move 1 meter in x
    robot_session.publish_pose(x=1, y=0, yaw=0)
    assert robot_session._odometry_accumulator_linear == 1.0
    assert robot_session._odometry_accumulator_angular == 0.0

    # Move 1 meter in y (total 2 meters)
    robot_session.publish_pose(x=1, y=1, yaw=0)
    assert robot_session._odometry_accumulator_linear == 2.0
    assert robot_session._odometry_accumulator_angular == 0.0

    # Rotate 90 degrees (pi/2)
    robot_session.publish_pose(x=1, y=1, yaw=math.pi / 2)
    assert robot_session._odometry_accumulator_linear == 2.0
    assert abs(robot_session._odometry_accumulator_angular - math.pi / 2) < 1e-6

    # Reset mock to ignore previous publish_pose calls
    robot_session.client.publish.reset_mock()

    # Publish odometry without arguments. Should use accumulated values
    # We mock time to ensure ts_start and ts are different
    robot_session.publish_odometry(ts=2000)

    robot_session.client.publish.assert_called_once()
    call_kwargs = robot_session.client.publish.call_args[1]
    odometry_msg = OdometryDataMessage()
    odometry_msg.ParseFromString(call_kwargs["payload"])

    assert odometry_msg.linear_distance == 2.0
    assert abs(odometry_msg.angular_distance - math.pi / 2) < 1e-6
    # Check timestamps
    assert odometry_msg.ts == 2000
    assert odometry_msg.ts_start < odometry_msg.ts

    # Verify accumulators are reset
    assert robot_session._odometry_accumulator_linear == 0.0
    assert robot_session._odometry_accumulator_angular == 0.0
    assert robot_session._last_odometry_ts == 2000

    # Reset mock
    robot_session.client.publish.reset_mock()
    # Reset throttling
    robot_session._publish_throttling["publish_odometry"]["last_ts"] = 0

    # Publish odometry WITH arguments (should override accumulated values)
    robot_session.publish_odometry(linear_distance=10.0, angular_distance=5.0, ts=3000)

    robot_session.client.publish.assert_called_once()
    call_kwargs = robot_session.client.publish.call_args[1]
    odometry_msg = OdometryDataMessage()
    odometry_msg.ParseFromString(call_kwargs["payload"])

    assert odometry_msg.linear_distance == 10.0
    assert odometry_msg.angular_distance == 5.0
    assert odometry_msg.ts == 3000
    assert odometry_msg.ts_start == 2000
