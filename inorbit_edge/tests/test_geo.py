#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for inorbit_edge.geo: UTM projection, GPS poses and map datums."""

import math

import pytest

from inorbit_edge.geo import (
    MapDatum,
    latlon_to_utm,
    latlon_to_utm_pose,
    utm_frame_id,
    utm_zone,
)

# Reference values: InOrbit ingest's GPS tests (north and south of the equator) and the
# Flatland/Gazebo outdoor sims' datum, whose map -> utm-10 transformation those sims
# apply
GOLDEN_GATE = (37.811072, -122.477603, 545982.64, 4184981.92, "utm-10")
CORDOBA = (-31.315845, -64.323323, 374080.68, 6534637.77, "utm-20-s")
SIM_DATUM = (37.39276686732228, -122.07953949815608)
SIM_TRANSFORMATION = [
    [0.999634192, -0.009753199, 581476.705],
    [0.009753199, 0.999634192, 4138842.183],
]


@pytest.mark.parametrize(
    "lat, lon, easting, northing, frame_id", [GOLDEN_GATE, CORDOBA]
)
def test_latlon_to_utm(lat, lon, easting, northing, frame_id):
    e, n = latlon_to_utm(lat, lon)
    assert e == pytest.approx(easting, abs=0.01)
    assert n == pytest.approx(northing, abs=0.01)
    assert utm_frame_id(lat, lon) == frame_id


def test_utm_zone_edges():
    assert utm_zone(-180) == 1
    assert utm_zone(179.999) == 60
    assert utm_zone(180) == 60


def test_latlon_to_utm_rejects_polar_latitudes():
    with pytest.raises(ValueError):
        latlon_to_utm(85, 0)


def test_map_datum_transformation_matches_the_sims():
    datum = MapDatum(*SIM_DATUM)
    assert datum.frame_id == "utm-10"
    for row, expected in zip(datum.transformation, SIM_TRANSFORMATION):
        assert row == pytest.approx(expected, abs=0.001)
    assert datum.transformation[2] == [0.0, 0.0, 1.0]


def test_map_datum_origin_and_heading():
    datum = MapDatum(*SIM_DATUM)
    e0, n0 = latlon_to_utm(*SIM_DATUM)
    easting, northing, yaw = datum.map_to_utm(0, 0, 0)
    assert (easting, northing) == pytest.approx((e0, n0), abs=0.001)
    # Facing east in the map is facing east rotated by the grid convergence in UTM
    assert yaw == pytest.approx(math.atan2(0.009753199, 0.999634192), abs=1e-6)


def test_map_datum_100_m_east_lands_100_m_east():
    datum = MapDatum(*SIM_DATUM)
    # The point 100 m east of the datum, projected directly
    phi = math.radians(SIM_DATUM[0])
    dlon = math.degrees(
        100 / (6378137 * math.cos(phi) / math.sqrt(1 - 0.00669438 * math.sin(phi) ** 2))
    )
    expected = latlon_to_utm(SIM_DATUM[0], SIM_DATUM[1] + dlon)
    easting, northing, _ = datum.map_to_utm(100, 0, 0)
    assert (easting, northing) == pytest.approx(expected, abs=0.01)


def test_map_datum_yaw_rotates_the_map():
    # A map whose x axis points north: map +x is UTM (about) +northing
    datum = MapDatum(*SIM_DATUM, yaw=math.pi / 2)
    e0, n0, _ = datum.map_to_utm(0, 0, 0)
    e1, n1, yaw = datum.map_to_utm(10, 0, 0)
    assert n1 - n0 == pytest.approx(10, abs=0.01)
    assert abs(e1 - e0) < 0.2
    assert yaw == pytest.approx(
        math.pi / 2 + math.atan2(0.009753199, 0.999634192), abs=1e-6
    )


def test_map_datum_wraps_yaw():
    datum = MapDatum(*SIM_DATUM)
    _, _, yaw = datum.map_to_utm(0, 0, math.pi)
    assert -math.pi <= yaw <= math.pi


def test_latlon_to_utm_pose_matches_the_sims():
    frame_id, easting, northing, yaw = latlon_to_utm_pose(*SIM_DATUM, 0.0)
    assert frame_id == "utm-10"
    assert easting == pytest.approx(SIM_TRANSFORMATION[0][2], abs=0.01)
    assert northing == pytest.approx(SIM_TRANSFORMATION[1][2], abs=0.01)
    # East in the world is turned by the grid convergence in the UTM grid
    convergence = math.atan2(SIM_TRANSFORMATION[1][0], SIM_TRANSFORMATION[0][0])
    assert yaw == pytest.approx(convergence, abs=1e-6)


def test_latlon_to_utm_pose_south():
    lat, lon, easting, northing, frame_id = CORDOBA
    got_frame_id, e, n, _ = latlon_to_utm_pose(lat, lon, 1.0)
    assert got_frame_id == frame_id
    assert e == pytest.approx(easting, abs=0.01)
    assert n == pytest.approx(northing, abs=0.01)
