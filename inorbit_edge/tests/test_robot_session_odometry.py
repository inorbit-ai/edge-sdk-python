#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import unittest.mock
import pytest
from inorbit_edge.robot import (
    RobotSession,
    RobotDistanceAccumulator,
    DISTANCE_ACCUMULATION_INTERVAL_LIMIT_MS,
)
from inorbit_edge.inorbit_pb2 import OdometryDataMessage
from inorbit_edge.types import Pose


class TestRobotSessionDistanceAccumulation:
    @pytest.fixture
    def robot_session(self, mock_mqtt_client, mock_inorbit_api, mock_sleep):
        """Create a robot session and disable throttling for testing."""
        with unittest.mock.patch("time.time", return_value=0):
            robot_session = RobotSession(
                robot_id="id_123",
                robot_name="name_123",
                api_key="apikey_123",
            )
        # Disable throttling for testing
        robot_session._publish_throttling["publish_pose"]["min_time_between_calls"] = 0
        robot_session._publish_throttling["publish_odometry"][
            "min_time_between_calls"
        ] = 0
        return robot_session

    def test_odometry_accumulation(self, robot_session):
        """RobotSession should accumulate angular and linear distance based on the
        published poses and publish them if values for them are not explicitly provided
        """

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
            abs(robot_session._distance_accumulator._angular_distance - math.pi / 2)
            < 1e-6
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

    def test_odometry_accumulation_reset(self, robot_session):
        """
        Verify that odometry accumulation continues correctly after
        publish_odometry() resets the accumulators.
        """

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

    def test_throttled_odometry_preserves_accumulator(self, robot_session):
        """Verify that throttled publish_odometry calls don't reset the accumulator."""

        # Re-enable throttling for odometry
        robot_session._publish_throttling["publish_odometry"][
            "min_time_between_calls"
        ] = 1

        # 1. Accumulate some distance
        robot_session.publish_pose(x=0, y=0, yaw=0)
        robot_session.publish_pose(x=1, y=0, yaw=0)
        assert robot_session._distance_accumulator._linear_distance == 1.0

        # 2. First publish_odometry call should pass throttling and reset accumulator
        robot_session.client.publish.reset_mock()
        robot_session.publish_odometry(ts=1000)
        robot_session.client.publish.assert_called_once()
        assert robot_session._distance_accumulator._linear_distance == 0.0

        # 3. Accumulate more distance
        robot_session.publish_pose(x=2, y=0, yaw=0)
        assert robot_session._distance_accumulator._linear_distance == 1.0

        # 4. Second publish_odometry call is throttled - should NOT reset accumulator
        robot_session.client.publish.reset_mock()
        robot_session.publish_odometry(ts=2000)
        robot_session.client.publish.assert_not_called()
        assert robot_session._distance_accumulator._linear_distance == 1.0

        # 5. Accumulate even more distance
        robot_session.publish_pose(x=3, y=0, yaw=0)
        assert robot_session._distance_accumulator._linear_distance == 2.0

        # 6. Reset throttling and publish again - should publish accumulated 2.0m
        robot_session._publish_throttling["publish_odometry"]["last_ts"] = 0
        robot_session.client.publish.reset_mock()
        robot_session.publish_odometry(ts=3000)

        robot_session.client.publish.assert_called_once()
        call_kwargs = robot_session.client.publish.call_args[1]
        odometry_msg = OdometryDataMessage()
        odometry_msg.ParseFromString(call_kwargs["payload"])

        assert odometry_msg.linear_distance == 2.0
        assert robot_session._distance_accumulator._linear_distance == 0.0

    def test_odometry_mixed_explicit_and_accumulated(self, robot_session):
        """Verify that it is possible to mix accumulated and explicit values."""

        # 1. Publish poses (accumulates linear and angular)
        # Initial pose
        robot_session.publish_pose(x=0, y=0, yaw=0)
        # Move 1m linear, rotate 90 deg
        robot_session.publish_pose(x=1, y=0, yaw=math.pi / 2)
        assert robot_session._distance_accumulator._linear_distance == 1.0
        assert robot_session._distance_accumulator._angular_distance == math.pi / 2

        # 2. Publish odometry with explicit linear distance but implicit angular
        # distance
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

    def test_odometry_accumulation_reset_on_frame_id_change(self, robot_session):
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
        robot_session.publish_pose(
            x=100, y=100, yaw=math.pi / 4, frame_id="different_map"
        )
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

    def test_odometry_accumulation_initial_pose_command(self, robot_session):
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
            abs(robot_session._distance_accumulator._angular_distance - math.pi / 2)
            < 1e-6
        )
        assert robot_session._distance_accumulator._start_ts == 0

    def test_odometry_accumulation_ignores_next_delta_on_offline(self, robot_session):
        """
        Test that when robot is offline (via get_state), the next pose delta is ignored.
        The pose after the next will be accumulated anyway.
        TODO(b-Tomas): implement a proactive way to set the robot online status.
        """

        # 1. Publish poses
        robot_session.publish_pose(x=0, y=0, yaw=0, frame_id="map")
        robot_session.publish_pose(x=1, y=0, yaw=0, frame_id="map")
        assert robot_session._distance_accumulator._linear_distance == 1.0
        assert robot_session._distance_accumulator._angular_distance == 0.0
        assert robot_session._distance_accumulator._start_ts == 0

        # 2. Set robot offline callback
        robot_session.set_online_status_callback(lambda: False)

        # 3. Trigger get_state command to detect robot is offline and discard next delta
        robot_session._handle_in_cmd(b"get_state")

        # 4. Publish another pose. This pose is ignored by the accumulator.
        robot_session.publish_pose(x=10, y=11, yaw=math.pi, frame_id="map")
        assert robot_session._distance_accumulator._linear_distance == 1.0
        assert robot_session._distance_accumulator._angular_distance == 0.0
        assert robot_session._distance_accumulator._start_ts == 0

        # 5. Reset robot online status callback
        robot_session.set_online_status_callback(lambda: True)

        # 6. Publish another pose. This pose is accumulated.
        robot_session.publish_pose(x=11, y=11, yaw=math.pi / 2, frame_id="map")
        assert robot_session._distance_accumulator._linear_distance == 2.0
        assert (
            abs(robot_session._distance_accumulator._angular_distance - math.pi / 2)
            < 1e-6
        )
        assert robot_session._distance_accumulator._start_ts == 0

    def test_odometry_accumulation_discards_delta_on_long_interval(self, robot_session):
        """Verify that deltas are discarded when time between poses exceeds limit."""

        # 1. Publish initial pose with timestamp
        robot_session.publish_pose(x=0, y=0, yaw=0, frame_id="map", ts=1000)
        assert robot_session._distance_accumulator._linear_distance == 0.0
        assert robot_session._distance_accumulator._angular_distance == 0.0

        # 2. Publish a pose shortly after (should accumulate)
        robot_session.publish_pose(x=1, y=0, yaw=0, frame_id="map", ts=2000)
        assert robot_session._distance_accumulator._linear_distance == 1.0
        assert robot_session._distance_accumulator._angular_distance == 0.0

        # 3. Publish a pose after the interval limit (should discard delta)
        # DISTANCE_ACCUMULATION_INTERVAL_LIMIT_MS is 30 seconds = 30000 ms
        # So a pose at 2000 + 30001 = 32001 should discard the delta
        interval_limit = DISTANCE_ACCUMULATION_INTERVAL_LIMIT_MS
        robot_session.publish_pose(
            x=10, y=10, yaw=math.pi, frame_id="map", ts=2000 + interval_limit + 1
        )
        # Distance should remain 1.0 (delta was discarded)
        assert robot_session._distance_accumulator._linear_distance == 1.0
        assert robot_session._distance_accumulator._angular_distance == 0.0

        # 4. Publish another pose shortly after (should accumulate from the last pose)
        robot_session.publish_pose(x=11, y=10, yaw=math.pi, frame_id="map", ts=32000)
        # Should accumulate 1 meter from (10, 10) to (11, 10)
        assert robot_session._distance_accumulator._linear_distance == 2.0
        assert robot_session._distance_accumulator._angular_distance == 0.0

    def test_odometry_accumulation_keeps_delta_within_interval_limit(
        self, robot_session
    ):
        """Verify deltas are NOT discarded when time between poses is within limit."""

        # 1. Publish initial pose with timestamp
        robot_session.publish_pose(x=0, y=0, yaw=0, frame_id="map", ts=1000)
        assert robot_session._distance_accumulator._linear_distance == 0.0

        # 2. Publish a pose just before the interval limit (should accumulate)
        # DISTANCE_ACCUMULATION_INTERVAL_LIMIT_MS is 30 seconds = 30000 ms
        # So a pose at 1000 + 30000 = 31000 should still accumulate (limit is >, not >=)
        interval_limit = DISTANCE_ACCUMULATION_INTERVAL_LIMIT_MS
        robot_session.publish_pose(
            x=1, y=0, yaw=0, frame_id="map", ts=1000 + interval_limit
        )
        assert robot_session._distance_accumulator._linear_distance == 1.0

        # 3. Publish another pose just before the limit again
        robot_session.publish_pose(x=2, y=0, yaw=0, frame_id="map", ts=61000)
        assert robot_session._distance_accumulator._linear_distance == 2.0

    def test_odometry_accumulation_interval_limit_with_frame_id_change(
        self, robot_session
    ):
        """
        Verify that both interval limit and frame_id change can cause delta discard.
        """

        # 1. Publish initial pose
        robot_session.publish_pose(x=0, y=0, yaw=0, frame_id="map", ts=1000)
        robot_session.publish_pose(x=1, y=0, yaw=0, frame_id="map", ts=2000)
        assert robot_session._distance_accumulator._linear_distance == 1.0

        # 2. Publish pose with different frame_id after long interval
        # Both conditions should cause discard, but the result is the same
        interval_limit = DISTANCE_ACCUMULATION_INTERVAL_LIMIT_MS
        robot_session.publish_pose(
            x=100,
            y=100,
            yaw=math.pi,
            frame_id="different_map",
            ts=1000 + interval_limit + 1,
        )
        assert robot_session._distance_accumulator._linear_distance == 1.0

        # 3. Continue in the new frame_id (should accumulate)
        robot_session.publish_pose(
            x=101, y=100, yaw=math.pi, frame_id="different_map", ts=32000
        )
        assert robot_session._distance_accumulator._linear_distance == 2.0

    def test_linear_distance_accumulation_can_be_disabled(
        self, mock_mqtt_client, mock_inorbit_api, mock_sleep
    ):
        """Verify that the accumulation can be disabled."""

        # Create a robot session with distance accumulation disabled
        with unittest.mock.patch("time.time", return_value=0):
            robot_session = RobotSession(
                robot_id="id_123",
                robot_name="name_123",
                api_key="apikey_123",
                estimate_distance_linear=False,
                estimate_distance_angular=True,
            )

        # Disable throttling for testing
        robot_session._publish_throttling["publish_pose"]["min_time_between_calls"] = 0
        robot_session._publish_throttling["publish_odometry"][
            "min_time_between_calls"
        ] = 0

        # 1. Publish poses
        robot_session.publish_pose(x=0, y=0, yaw=0, frame_id="map")
        robot_session.publish_pose(x=1, y=0, yaw=math.pi / 2, frame_id="map")

        # 2. Publish odometry
        robot_session.publish_odometry(ts=2000)
        call_kwargs = robot_session.client.publish.call_args[1]
        odometry_msg = OdometryDataMessage()
        odometry_msg.ParseFromString(call_kwargs["payload"])

        assert odometry_msg.linear_distance == 0.0
        assert abs(odometry_msg.angular_distance - math.pi / 2) < 1e-6
        assert odometry_msg.ts == 2000
        assert odometry_msg.ts_start == 0

    def test_angular_distance_accumulation_can_be_disabled(
        self, mock_mqtt_client, mock_inorbit_api, mock_sleep
    ):
        """Verify that the angular distance accumulation can be disabled."""

        # Create a robot session with angular distance accumulation disabled
        with unittest.mock.patch("time.time", return_value=0):
            robot_session = RobotSession(
                robot_id="id_123",
                robot_name="name_123",
                api_key="apikey_123",
                estimate_distance_linear=True,
                estimate_distance_angular=False,
            )

        # Disable throttling for testing
        robot_session._publish_throttling["publish_pose"]["min_time_between_calls"] = 0
        robot_session._publish_throttling["publish_odometry"][
            "min_time_between_calls"
        ] = 0

        # 1. Publish poses
        robot_session.publish_pose(x=0, y=0, yaw=0, frame_id="map")
        robot_session.publish_pose(x=1, y=0, yaw=math.pi / 2, frame_id="map")

        # 2. Publish odometry
        robot_session.publish_odometry(ts=2000)
        call_kwargs = robot_session.client.publish.call_args[1]
        odometry_msg = OdometryDataMessage()
        odometry_msg.ParseFromString(call_kwargs["payload"])

        assert odometry_msg.linear_distance == 1.0
        assert odometry_msg.angular_distance == 0.0
        assert odometry_msg.ts == 2000
        assert odometry_msg.ts_start == 0

    def test_both_distances_accumulation_can_be_disabled(
        self, mock_mqtt_client, mock_inorbit_api, mock_sleep
    ):
        """Verify that both distances accumulation can be disabled."""

        # Create a robot session with both distances accumulation disabled
        with unittest.mock.patch("time.time", return_value=0):
            robot_session = RobotSession(
                robot_id="id_123",
                robot_name="name_123",
                api_key="apikey_123",
                estimate_distance_linear=False,
                estimate_distance_angular=False,
            )

        # Disable throttling for testing
        robot_session._publish_throttling["publish_pose"]["min_time_between_calls"] = 0
        robot_session._publish_throttling["publish_odometry"][
            "min_time_between_calls"
        ] = 0

        # 1. Publish poses
        robot_session.publish_pose(x=0, y=0, yaw=0, frame_id="map")
        robot_session.publish_pose(x=1, y=0, yaw=math.pi / 2, frame_id="map")

        # 2. Publish odometry
        robot_session.publish_odometry(ts=2000)
        call_kwargs = robot_session.client.publish.call_args[1]
        odometry_msg = OdometryDataMessage()
        odometry_msg.ParseFromString(call_kwargs["payload"])

        assert odometry_msg.linear_distance == 0.0
        assert odometry_msg.angular_distance == 0.0
        assert odometry_msg.ts == 2000
        assert odometry_msg.ts_start == 0


class TestRobotDistanceAccumulator:
    """Unit tests for RobotDistanceAccumulator class."""

    @pytest.fixture
    def accumulator(self):
        """Create a default accumulator with both estimates enabled."""
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=1.0):
            return RobotDistanceAccumulator()

    def test_initialization_default(self):
        """Test default initialization with both estimates enabled."""
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=1.0):
            acc = RobotDistanceAccumulator()
            assert acc._estimate_distance_linear is True
            assert acc._estimate_distance_angular is True
            assert acc.last_pose is None
            assert acc._linear_distance == 0.0
            assert acc._angular_distance == 0.0
            assert acc._start_ts == 1000

    def test_initialization_linear_disabled(self):
        """Test initialization with linear distance estimation disabled."""
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=2.0):
            acc = RobotDistanceAccumulator(estimate_distance_linear=False)
            assert acc._estimate_distance_linear is False
            assert acc._estimate_distance_angular is True
            assert acc._start_ts == 2000

    def test_initialization_angular_disabled(self):
        """Test initialization with angular distance estimation disabled."""
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=3.0):
            acc = RobotDistanceAccumulator(estimate_distance_angular=False)
            assert acc._estimate_distance_linear is True
            assert acc._estimate_distance_angular is False
            assert acc._start_ts == 3000

    def test_initialization_both_disabled(self):
        """Test initialization with both estimates disabled."""
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=4.0):
            acc = RobotDistanceAccumulator(
                estimate_distance_linear=False, estimate_distance_angular=False
            )
            assert acc._estimate_distance_linear is False
            assert acc._estimate_distance_angular is False
            assert acc._start_ts == 4000

    def test_reset_with_timestamp(self, accumulator):
        """Test reset with explicit timestamp."""
        accumulator._linear_distance = 5.0
        accumulator._angular_distance = 2.0
        accumulator._reset(ts=5000)
        assert accumulator._linear_distance == 0.0
        assert accumulator._angular_distance == 0.0
        assert accumulator._start_ts == 5000

    def test_reset_without_timestamp(self):
        """Test reset without timestamp uses current time."""
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=6.0):
            acc = RobotDistanceAccumulator()
            acc._linear_distance = 10.0
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=7.0):
            acc._reset()
        assert acc._linear_distance == 0.0
        assert acc._angular_distance == 0.0
        assert acc._start_ts == 7000

    def test_accumulate_first_pose(self, accumulator):
        """Test that first pose doesn't accumulate distance."""
        pose = Pose(frame_id="map", x=1.0, y=2.0, theta=0.5)
        accumulator.accumulate(pose)
        assert accumulator._linear_distance == 0.0
        assert accumulator._angular_distance == 0.0
        assert accumulator.last_pose.frame_id == pose.frame_id
        assert accumulator.last_pose.x == pose.x
        assert accumulator.last_pose.y == pose.y
        assert accumulator.last_pose.theta == pose.theta

    def test_accumulate_linear_movement(self, accumulator):
        """Test accumulation of linear movement."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=3.0, y=4.0, theta=0.0)
        accumulator.accumulate(pose1)
        accumulator.accumulate(pose2)
        assert accumulator._linear_distance == 5.0
        assert accumulator._angular_distance == 0.0
        assert accumulator.last_pose.frame_id == pose2.frame_id
        assert accumulator.last_pose.x == pose2.x
        assert accumulator.last_pose.y == pose2.y
        assert accumulator.last_pose.theta == pose2.theta

    def test_accumulate_angular_movement(self, accumulator):
        """Test accumulation of angular movement."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=math.pi / 2)
        accumulator.accumulate(pose1)
        accumulator.accumulate(pose2)
        assert accumulator._linear_distance == 0.0
        assert accumulator._angular_distance == pytest.approx(math.pi / 2)
        assert accumulator.last_pose.frame_id == pose2.frame_id
        assert accumulator.last_pose.x == pose2.x
        assert accumulator.last_pose.y == pose2.y
        assert accumulator.last_pose.theta == pose2.theta

    def test_accumulate_both_movements(self, accumulator):
        """Test accumulation of both linear and angular movement."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=3.0, y=4.0, theta=math.pi / 4)
        accumulator.accumulate(pose1)
        accumulator.accumulate(pose2)
        assert accumulator._linear_distance == 5.0
        assert accumulator._angular_distance == pytest.approx(math.pi / 4)
        assert accumulator.last_pose.frame_id == pose2.frame_id
        assert accumulator.last_pose.x == pose2.x
        assert accumulator.last_pose.y == pose2.y
        assert accumulator.last_pose.theta == pose2.theta

    def test_accumulate_multiple_poses(self, accumulator):
        """Test accumulation across multiple poses."""
        poses = [
            Pose(frame_id="map", x=0.0, y=0.0, theta=0.0),
            Pose(frame_id="map", x=1.0, y=0.0, theta=0.0),
            Pose(frame_id="map", x=1.0, y=1.0, theta=math.pi / 2),
            Pose(frame_id="map", x=2.0, y=1.0, theta=math.pi / 2),
        ]
        for pose in poses:
            accumulator.accumulate(pose)
        assert accumulator._linear_distance == 3.0
        assert accumulator._angular_distance == pytest.approx(math.pi / 2)
        assert accumulator.last_pose.frame_id == poses[-1].frame_id
        assert accumulator.last_pose.x == poses[-1].x
        assert accumulator.last_pose.y == poses[-1].y
        assert accumulator.last_pose.theta == poses[-1].theta

    def test_accumulate_with_discard_delta(self, accumulator):
        """Test that discard_delta=True doesn't accumulate but updates last_pose."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=10.0, y=10.0, theta=math.pi)
        accumulator.accumulate(pose1)
        accumulator.accumulate(pose2, discard_delta=True)
        assert accumulator._linear_distance == 0.0
        assert accumulator._angular_distance == 0.0
        assert accumulator.last_pose.frame_id == pose2.frame_id
        assert accumulator.last_pose.x == pose2.x
        assert accumulator.last_pose.y == pose2.y
        assert accumulator.last_pose.theta == pose2.theta

    def test_accumulate_discard_delta_after_accumulation(self, accumulator):
        """Test discard_delta after some accumulation."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=1.0, y=0.0, theta=0.0)
        pose3 = Pose(frame_id="map", x=100.0, y=100.0, theta=math.pi)
        accumulator.accumulate(pose1)
        accumulator.accumulate(pose2)
        assert accumulator._linear_distance == 1.0
        accumulator.accumulate(pose3, discard_delta=True)
        assert accumulator._linear_distance == 1.0
        assert accumulator.last_pose.frame_id == pose3.frame_id
        assert accumulator.last_pose.x == pose3.x
        assert accumulator.last_pose.y == pose3.y
        assert accumulator.last_pose.theta == pose3.theta

    def test_get_values_and_reset_returns_correct_values(self, accumulator):
        """Test that get_values_and_reset returns accumulated values."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=3.0, y=4.0, theta=math.pi / 2)
        accumulator.accumulate(pose1)
        accumulator.accumulate(pose2)
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=2.0):
            linear, angular, start_ts = accumulator.get_values_and_reset()
        assert linear == 5.0
        assert angular == pytest.approx(math.pi / 2)
        assert start_ts == 1000
        assert accumulator._linear_distance == 0.0
        assert accumulator._angular_distance == 0.0

    def test_get_values_and_reset_with_timestamp(self, accumulator):
        """Test get_values_and_reset with explicit timestamp."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=1.0, y=0.0, theta=0.0)
        accumulator.accumulate(pose1)
        accumulator.accumulate(pose2)
        linear, angular, start_ts = accumulator.get_values_and_reset(ts=5000)
        assert linear == 1.0
        assert angular == 0.0
        assert start_ts == 1000
        assert accumulator._start_ts == 5000

    def test_get_values_and_reset_respects_linear_flag(self):
        """Test that get_values_and_reset respects estimate_distance_linear flag."""
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=1.0):
            acc = RobotDistanceAccumulator(estimate_distance_linear=False)
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=10.0, y=0.0, theta=0.0)
        acc.accumulate(pose1)
        acc.accumulate(pose2)
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=2.0):
            linear, angular, _ = acc.get_values_and_reset()
        assert linear == 0.0
        assert acc._linear_distance == 0.0

    def test_get_values_and_reset_respects_angular_flag(self):
        """Test that get_values_and_reset respects estimate_distance_angular flag."""
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=1.0):
            acc = RobotDistanceAccumulator(estimate_distance_angular=False)
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=math.pi)
        acc.accumulate(pose1)
        acc.accumulate(pose2)
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=2.0):
            linear, angular, _ = acc.get_values_and_reset()
        assert angular == 0.0
        assert acc._angular_distance == 0.0

    def test_get_values_and_reset_respects_both_flags(self):
        """Test that get_values_and_reset respects both flags."""
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=1.0):
            acc = RobotDistanceAccumulator(
                estimate_distance_linear=False, estimate_distance_angular=False
            )
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=10.0, y=0.0, theta=math.pi)
        acc.accumulate(pose1)
        acc.accumulate(pose2)
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=2.0):
            linear, angular, _ = acc.get_values_and_reset()
        assert linear == 0.0
        assert angular == 0.0
        assert acc._linear_distance == 0.0
        assert acc._angular_distance == 0.0

    def test_discard_next_delta(self, accumulator):
        """Test that discard_next_delta sets last_pose to None."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=1.0, y=0.0, theta=0.0)
        accumulator.accumulate(pose1)
        accumulator.accumulate(pose2)
        assert accumulator._linear_distance == 1.0
        accumulator.discard_next_delta()
        assert accumulator.last_pose is None

    def test_discard_next_delta_prevents_accumulation(self, accumulator):
        """Test that after discard_next_delta, next accumulate doesn't accumulate."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=1.0, y=0.0, theta=0.0)
        pose3 = Pose(frame_id="map", x=2.0, y=0.0, theta=0.0)
        accumulator.accumulate(pose1)
        accumulator.accumulate(pose2)
        assert accumulator._linear_distance == 1.0
        accumulator.discard_next_delta()
        accumulator.accumulate(pose3)
        assert accumulator._linear_distance == 1.0
        assert accumulator.last_pose.frame_id == pose3.frame_id
        assert accumulator.last_pose.x == pose3.x
        assert accumulator.last_pose.y == pose3.y
        assert accumulator.last_pose.theta == pose3.theta

    def test_discard_next_delta_then_accumulate_again(self, accumulator):
        """Test accumulation continues after discard_next_delta."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=1.0, y=0.0, theta=0.0)
        pose3 = Pose(frame_id="map", x=100.0, y=0.0, theta=0.0)
        pose4 = Pose(frame_id="map", x=101.0, y=0.0, theta=0.0)
        accumulator.accumulate(pose1)
        accumulator.accumulate(pose2)
        assert accumulator._linear_distance == 1.0
        accumulator.discard_next_delta()
        accumulator.accumulate(pose3)
        assert accumulator._linear_distance == 1.0
        accumulator.accumulate(pose4)
        assert accumulator._linear_distance == 2.0
        assert accumulator.last_pose.frame_id == pose4.frame_id
        assert accumulator.last_pose.x == pose4.x
        assert accumulator.last_pose.y == pose4.y
        assert accumulator.last_pose.theta == pose4.theta

    def test_get_values_and_reset_preserves_last_pose(self, accumulator):
        """Test that get_values_and_reset doesn't reset last_pose."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=1.0, y=0.0, theta=0.0)
        accumulator.accumulate(pose1)
        accumulator.accumulate(pose2)
        with unittest.mock.patch("inorbit_edge.robot.time.time", return_value=2.0):
            accumulator.get_values_and_reset()
        assert accumulator.last_pose.frame_id == pose2.frame_id
        assert accumulator.last_pose.x == pose2.x
        assert accumulator.last_pose.y == pose2.y
        assert accumulator.last_pose.theta == pose2.theta
        assert accumulator._linear_distance == 0.0
        assert accumulator._angular_distance == 0.0
