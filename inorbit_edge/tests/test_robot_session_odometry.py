#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import unittest.mock
import pytest
from inorbit_edge.robot import RobotSession, DISTANCE_ACCUMULATION_INTERVAL_LIMIT_MS
from inorbit_edge.inorbit_pb2 import OdometryDataMessage


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
        # ODOMETRY_ACCUMULATION_INTERVAL_LIMIT_MS is 30 seconds = 30000 ms
        # So a pose at 1000 + 30001 = 31001 should discard the delta
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
        # ODOMETRY_ACCUMULATION_INTERVAL_LIMIT_MS is 30 seconds = 30000 ms
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
