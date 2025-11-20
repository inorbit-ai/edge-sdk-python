#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import unittest.mock
import pytest
from inorbit_edge.robot import RobotSession
from inorbit_edge.inorbit_pb2 import OdometryDataMessage


@pytest.fixture
def robot_session(mock_mqtt_client, mock_inorbit_api, mock_sleep):
    """Create a robot session and disable throttling for testing."""
    with unittest.mock.patch("time.time", return_value=0):
        robot_session = RobotSession(
            robot_id="id_123",
            robot_name="name_123",
            api_key="apikey_123",
        )
    # Disable throttling for testing
    robot_session._publish_throttling["publish_pose"]["min_time_between_calls"] = 0
    robot_session._publish_throttling["publish_odometry"]["min_time_between_calls"] = 0
    return robot_session


def test_odometry_accumulation(robot_session):
    """RobotSession should accumulate angular and linear distance based on the
    published poses and publish them if values for them are not explicitly provided"""

    # Initial state should be 0
    assert robot_session._distance_accumulator._linear_distance == 0.0
    assert robot_session._distance_accumulator._angular_distance == 0.0
    assert robot_session._distance_accumulator._start_ts == 0

    # Publish first pose (no distance accumulated yet)
    robot_session.publish_pose(x=0, y=0, yaw=0)
    assert robot_session._distance_accumulator._linear_distance == 0.0
    assert robot_session._distance_accumulator._angular_distance == 0.0
    assert robot_session._distance_accumulator._start_ts == 0

    # Move 1 meter in x
    robot_session.publish_pose(x=1, y=0, yaw=0)
    assert robot_session._distance_accumulator._linear_distance == 1.0
    assert robot_session._distance_accumulator._angular_distance == 0.0
    assert robot_session._distance_accumulator._start_ts == 0

    # Move 1 meter in y (total 2 meters)
    robot_session.publish_pose(x=1, y=1, yaw=0)
    assert robot_session._distance_accumulator._linear_distance == 2.0
    assert robot_session._distance_accumulator._angular_distance == 0.0
    assert robot_session._distance_accumulator._start_ts == 0

    # Rotate 90 degrees (pi/2)
    robot_session.publish_pose(x=1, y=1, yaw=math.pi / 2)
    assert robot_session._distance_accumulator._linear_distance == 2.0
    assert (
        abs(robot_session._distance_accumulator._angular_distance - math.pi / 2) < 1e-6
    )
    assert robot_session._distance_accumulator._start_ts == 0

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
    assert odometry_msg.ts_start == 0

    # Verify accumulators are reset
    assert robot_session._distance_accumulator._linear_distance == 0.0
    assert robot_session._distance_accumulator._angular_distance == 0.0
    assert robot_session._distance_accumulator._start_ts == 2000

    # Reset mock
    robot_session.client.publish.reset_mock()
    # Reset throttling
    robot_session._publish_throttling["publish_odometry"]["last_ts"] = 0

    # Publish odometry with arguments (should override accumulated values)
    robot_session.publish_odometry(
        linear_distance=10.0, angular_distance=5.0, ts=3000, ts_start=1500
    )

    robot_session.client.publish.assert_called_once()
    call_kwargs = robot_session.client.publish.call_args[1]
    odometry_msg = OdometryDataMessage()
    odometry_msg.ParseFromString(call_kwargs["payload"])

    assert odometry_msg.ts == 3000
    assert odometry_msg.ts_start == 1500


def test_odometry_accumulation_reset(robot_session):
    """Verify that odometry accumulation continues correctly after publish_odometry()
    resets the accumulators."""

    # 1. Publish poses and accumulate distance
    robot_session.publish_pose(x=0, y=0, yaw=0)
    robot_session.publish_pose(x=1, y=0, yaw=0)
    assert robot_session._distance_accumulator._linear_distance == 1.0
    assert robot_session._distance_accumulator._angular_distance == 0.0
    assert robot_session._distance_accumulator._start_ts == 0

    # 2. Call publish_odometry() (resets accumulators)
    robot_session.client.publish.reset_mock()
    robot_session.publish_odometry(ts=2000)

    # Verify reset happened
    assert robot_session._distance_accumulator._linear_distance == 0.0
    assert robot_session._distance_accumulator._angular_distance == 0.0
    assert robot_session._distance_accumulator._start_ts == 2000

    # 3. Publish more poses
    robot_session.publish_pose(x=1, y=1, yaw=0)  # +1m linear
    assert robot_session._distance_accumulator._linear_distance == 1.0
    assert robot_session._distance_accumulator._angular_distance == 0.0
    assert robot_session._distance_accumulator._start_ts == 2000

    # 4. Call publish_odometry() again
    robot_session.client.publish.reset_mock()
    # Reset throttling
    robot_session.publish_odometry(ts=3000, ts_start=1500)

    # 5. Verify that only the distance from step 3 is reported
    robot_session.client.publish.assert_called_once()
    call_kwargs = robot_session.client.publish.call_args[1]
    odometry_msg = OdometryDataMessage()
    odometry_msg.ParseFromString(call_kwargs["payload"])

    assert odometry_msg.linear_distance == 1.0
    assert odometry_msg.ts == 3000
    assert odometry_msg.ts_start == 1500


def test_odometry_mixed_explicit_and_accumulated(robot_session):
    """Verify that it is possible to mix accumulated and explicit values."""

    # 1. Publish poses (accumulates linear and angular)
    # Initial pose
    robot_session.publish_pose(x=0, y=0, yaw=0)
    # Move 1m linear, rotate 90 deg
    robot_session.publish_pose(x=1, y=0, yaw=math.pi / 2)
    assert robot_session._distance_accumulator._linear_distance == 1.0
    assert robot_session._distance_accumulator._angular_distance == math.pi / 2

    # 2. Publish odometry with explicit linear distance but implicit angular distance
    robot_session.publish_odometry(linear_distance=10.0, ts=2000)

    # 3. Verify message content
    call_kwargs = robot_session.client.publish.call_args[1]
    odometry_msg = OdometryDataMessage()
    odometry_msg.ParseFromString(call_kwargs["payload"])

    # Linear should be the explicit value (10.0)
    assert odometry_msg.linear_distance == 10.0
    # Angular should be the accumulated value (pi/2)
    assert abs(odometry_msg.angular_distance - math.pi / 2) < 1e-6

    # 4. Verify both accumulators are reset
    # (Because we published an odometry report, the interval is "complete" for both)
    assert robot_session._distance_accumulator._linear_distance == 0.0
    assert robot_session._distance_accumulator._angular_distance == 0.0


def test_odometry_accumulation_reset_on_frame_id_change(robot_session):
    """Verify that the accumulator is not reset on a frame_id change."""

    # 1. Publish poses (accumulates linear and angular)
    # Initial pose
    robot_session.publish_pose(x=0, y=0, yaw=0, frame_id="map")
    # Move 1m linear, rotate 90 deg
    robot_session.publish_pose(x=1, y=0, yaw=math.pi / 2, frame_id="map")
    assert robot_session._distance_accumulator._linear_distance == 1.0
    assert robot_session._distance_accumulator._angular_distance == math.pi / 2
    assert robot_session._distance_accumulator._start_ts == 0

    # 2. Publish poses with different frame_id (should not change nor reset the
    # accumulator values)
    robot_session.publish_pose(x=100, y=100, yaw=math.pi / 4, frame_id="different_map")
    assert robot_session._distance_accumulator._linear_distance == 1.0
    assert robot_session._distance_accumulator._angular_distance == math.pi / 2
    assert robot_session._distance_accumulator._start_ts == 0

    # 3. Continue publishing poses in the new frame_id (should accumulate the delta)
    robot_session.publish_pose(
        x=103, y=104, yaw=math.pi * 3 / 4, frame_id="different_map"
    )
    assert robot_session._distance_accumulator._linear_distance == 6.0
    assert robot_session._distance_accumulator._angular_distance == math.pi
    assert robot_session._distance_accumulator._start_ts == 0

    # 3. Publish odometry
    robot_session.publish_odometry(ts=3000)
    call_kwargs = robot_session.client.publish.call_args[1]
    odometry_msg = OdometryDataMessage()
    odometry_msg.ParseFromString(call_kwargs["payload"])

    assert odometry_msg.linear_distance == 6.0
    assert abs(odometry_msg.angular_distance - math.pi) < 1e-6
    assert odometry_msg.ts == 3000
    assert odometry_msg.ts_start == 0

    assert robot_session._distance_accumulator._linear_distance == 0.0
    assert robot_session._distance_accumulator._angular_distance == 0.0
    assert robot_session._distance_accumulator._start_ts == 3000


def test_odometry_accumulation_initial_pose_command(robot_session):
    """Verify that the next pose is not accumulated if the initial pose command is
    received, but the accumulator is not reset.
    """

    # 1. Publish poses
    robot_session.publish_pose(x=0, y=0, yaw=0, frame_id="map")
    robot_session.publish_pose(x=1, y=0, yaw=0, frame_id="map")
    assert robot_session._distance_accumulator._linear_distance == 1.0
    assert robot_session._distance_accumulator._angular_distance == 0.0
    assert robot_session._distance_accumulator._start_ts == 0

    # 2. Publish initial pose command
    robot_session._handle_initial_pose("0|1000|10|10|0.7854".encode())
    assert robot_session._distance_accumulator._linear_distance == 1.0
    assert robot_session._distance_accumulator._angular_distance == 0.0
    assert robot_session._distance_accumulator._start_ts == 0

    # 3. Publish another pose. This pose is ignored by the accumulator.
    robot_session.publish_pose(x=10, y=11, yaw=math.pi, frame_id="map")
    assert robot_session._distance_accumulator._linear_distance == 1.0
    assert robot_session._distance_accumulator._angular_distance == 0.0
    assert robot_session._distance_accumulator._start_ts == 0

    # 4. Publish another pose. This pose is accumulated.
    robot_session.publish_pose(x=11, y=11, yaw=math.pi / 2, frame_id="map")
    assert robot_session._distance_accumulator._linear_distance == 2.0
    assert (
        abs(robot_session._distance_accumulator._angular_distance - math.pi / 2) < 1e-6
    )
    assert robot_session._distance_accumulator._start_ts == 0
