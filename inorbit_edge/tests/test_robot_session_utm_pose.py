#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for RobotSession's outdoor methods: UTM and geo poses, GPS fixes."""

from unittest.mock import MagicMock

import pytest

from inorbit_edge.geo import latlon_to_utm_pose
from inorbit_edge.inorbit_pb2 import (
    GpsFixMessage,
    LocationAndPoseMessage,
    PoseMessage,
)
from inorbit_edge.robot import (
    MQTT_SUBTOPIC_GPS_FIX,
    MQTT_SUBTOPIC_POSE,
    MQTT_SUBTOPIC_UTM_POSE,
    RobotSession,
)

SIM_DATUM = (37.39276686732228, -122.07953949815608)
SIM_UTM = (581476.705, 4138842.183)


@pytest.fixture
def robot_session(mock_sleep):
    session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )
    session.publish_protobuf = MagicMock()
    return session


def published(session):
    """(topic, message) of the only publish_protobuf call."""
    session.publish_protobuf.assert_called_once()
    topic, msg = session.publish_protobuf.call_args.args[:2]
    return topic, msg


def test_publish_pose_stays_in_the_map_frame(robot_session):
    robot_session.publish_pose(1.0, 2.0, 0.5)
    topic, msg = published(robot_session)
    assert topic == MQTT_SUBTOPIC_POSE
    assert isinstance(msg, LocationAndPoseMessage)
    assert msg.frame_id == "map"


def test_publish_utm_pose(robot_session):
    robot_session.publish_utm_pose(*SIM_UTM, 0.5, "utm-10", ts=1234)
    topic, msg = published(robot_session)
    assert topic == MQTT_SUBTOPIC_UTM_POSE
    assert isinstance(msg, PoseMessage)
    (pose,) = msg.poses
    assert pose.frame_id == "utm-10"
    assert pose.ts == 1234
    # Split into offset + position, so 32-bit floats keep millimeters
    assert pose.offset_x % 10000 == 0 and pose.offset_y % 10000 == 0
    assert abs(pose.pos_x) <= 5000 and abs(pose.pos_y) <= 5000
    assert pose.offset_x + pose.pos_x == pytest.approx(SIM_UTM[0], abs=0.001)
    assert pose.offset_y + pose.pos_y == pytest.approx(SIM_UTM[1], abs=0.001)
    assert pose.yaw == pytest.approx(0.5, abs=1e-6)


def test_publish_utm_pose_tracks_the_pose(robot_session):
    robot_session.publish_utm_pose(*SIM_UTM, 0.5, "utm-10")
    assert robot_session._last_pose.frame_id == "utm-10"
    assert (robot_session._last_pose.x, robot_session._last_pose.y) == SIM_UTM


def test_publish_utm_pose_shares_publish_pose_throttling(robot_session):
    robot_session.publish_pose(1.0, 2.0, 0.5)
    robot_session.publish_utm_pose(*SIM_UTM, 0.5, "utm-10")
    robot_session.publish_protobuf.assert_called_once()


def test_publish_geo_pose(robot_session):
    robot_session.publish_geo_pose(*SIM_DATUM, 0.5, ts=1234)
    topic, msg = published(robot_session)
    frame_id, easting, northing, yaw = latlon_to_utm_pose(*SIM_DATUM, 0.5)
    assert topic == MQTT_SUBTOPIC_UTM_POSE
    (pose,) = msg.poses
    assert pose.frame_id == frame_id == "utm-10"
    assert pose.offset_x + pose.pos_x == pytest.approx(easting, abs=0.001)
    assert pose.offset_y + pose.pos_y == pytest.approx(northing, abs=0.001)
    assert pose.yaw == pytest.approx(yaw, abs=1e-6)


def test_publish_gps_fix(robot_session):
    robot_session.publish_gps_fix(*SIM_DATUM, altitude=10.0, ts=1234)
    topic, msg = published(robot_session)
    assert topic == MQTT_SUBTOPIC_GPS_FIX
    assert isinstance(msg, GpsFixMessage)
    assert (msg.latitude, msg.longitude) == pytest.approx(SIM_DATUM)
    assert msg.altitude == pytest.approx(10.0)
    assert msg.ts == 1234
    assert not msg.has_accuracy and not msg.has_bearing


def test_publish_gps_fix_with_accuracy_and_bearing(robot_session):
    robot_session.publish_gps_fix(*SIM_DATUM, accuracy_meters=0.02, bearing=90.0)
    _, msg = published(robot_session)
    assert msg.has_accuracy and msg.accuracy_meters == pytest.approx(0.02)
    assert msg.has_bearing and msg.bearing == pytest.approx(90.0)


def test_poses_send_no_gps_fix(robot_session):
    robot_session.publish_geo_pose(*SIM_DATUM, 0.5)
    topic, _ = published(robot_session)
    assert topic == MQTT_SUBTOPIC_UTM_POSE
