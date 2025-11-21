#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import pytest
from inorbit_edge.types import Pose
from inorbit_edge.utils import calculate_pose_delta


class TestCalculatePoseDelta:
    """Tests for calculate_pose_delta function."""

    def test_same_pose(self):
        """Test that same pose returns zero distance."""
        pose = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        linear_delta, angular_delta = calculate_pose_delta(pose, pose)
        assert linear_delta == 0.0
        assert angular_delta == 0.0

    def test_linear_movement_only(self):
        """Test linear distance calculation with no rotation."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=3.0, y=4.0, theta=0.0)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert linear_delta == 5.0
        assert angular_delta == 0.0

    def test_angular_movement_only(self):
        """Test angular distance calculation with no linear movement."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=math.pi / 2)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert linear_delta == 0.0
        assert angular_delta == pytest.approx(math.pi / 2)

    def test_both_linear_and_angular_movement(self):
        """Test calculation with both linear and angular movement."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=3.0, y=4.0, theta=math.pi / 4)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert linear_delta == 5.0
        assert angular_delta == pytest.approx(math.pi / 4)

    def test_angle_normalization_small_difference(self):
        """Test that small angle differences are preserved."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=math.pi / 6)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert angular_delta == pytest.approx(math.pi / 6)

    def test_angle_normalization_large_difference(self):
        """Test that large angle differences (> pi) are normalized to smaller angle."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=3 * math.pi / 2)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert angular_delta == pytest.approx(math.pi / 2)

    def test_angle_normalization_wraparound(self):
        """Test angle normalization when wrapping around 2π."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=2 * math.pi)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert angular_delta == pytest.approx(0.0)

    def test_angle_normalization_wraparound_plus_small(self):
        """Test angle normalization when wrapping around 2π with small offset."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=2 * math.pi + math.pi / 4)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert angular_delta == pytest.approx(math.pi / 4)

    def test_angle_normalization_exactly_pi(self):
        """Test angle normalization when difference is exactly π."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=math.pi)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert angular_delta == pytest.approx(math.pi)

    def test_angle_normalization_negative_angles(self):
        """Test angle normalization with negative angles."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=-math.pi / 2)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=math.pi / 2)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert angular_delta == pytest.approx(math.pi)

    def test_angle_normalization_large_negative_difference(self):
        """Test angle normalization with large negative angle difference."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=math.pi / 2)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=-math.pi / 2)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert angular_delta == pytest.approx(math.pi)

    def test_linear_distance_negative_coordinates(self):
        """Test linear distance calculation with negative coordinates."""
        pose1 = Pose(frame_id="map", x=-1.0, y=-1.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=2.0, y=2.0, theta=0.0)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert linear_delta == pytest.approx(3 * math.sqrt(2))
        assert angular_delta == 0.0

    def test_linear_distance_commutative(self):
        """Test that linear distance is commutative (order doesn't matter)."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=3.0, y=4.0, theta=math.pi / 4)
        linear_delta1, angular_delta1 = calculate_pose_delta(pose1, pose2)
        linear_delta2, angular_delta2 = calculate_pose_delta(pose2, pose1)
        assert linear_delta1 == linear_delta2
        assert angular_delta1 == angular_delta2

    def test_angle_normalization_multiple_wraparounds(self):
        """Test angle normalization with multiple 2π wraparounds."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=4 * math.pi + math.pi / 3)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert angular_delta == pytest.approx(math.pi / 3)

    def test_angle_normalization_close_to_2pi(self):
        """Test angle normalization when difference is close to 2π."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=2 * math.pi - 0.1)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert angular_delta == pytest.approx(0.1)

    def test_angle_normalization_just_over_pi(self):
        """Test angle normalization when difference is just over π."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="map", x=0.0, y=0.0, theta=math.pi + 0.1)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert angular_delta == pytest.approx(math.pi - 0.1)

    def test_different_frame_ids(self):
        """Test that frame_id doesn't affect the calculation."""
        pose1 = Pose(frame_id="map", x=0.0, y=0.0, theta=0.0)
        pose2 = Pose(frame_id="odom", x=3.0, y=4.0, theta=math.pi / 2)
        linear_delta, angular_delta = calculate_pose_delta(pose1, pose2)
        assert linear_delta == 5.0
        assert angular_delta == pytest.approx(math.pi / 2)
