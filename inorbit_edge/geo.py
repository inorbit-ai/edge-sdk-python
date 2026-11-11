#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Geographic helpers for outdoor robots: WGS84 to UTM.

InOrbit shows outdoor robots on UTM maps, one per zone, with frame ids ``utm-<zone>``
(``utm-<zone>-s`` south of the equator), and creates a robot's UTM map by itself the
first time a pose in such a frame arrives (``RobotSession.publish_utm_pose``). These
helpers give connectors that pose: :func:`latlon_to_utm_pose` from a GPS position and
heading, and :class:`MapDatum` from a pose in a local map frame anchored to a datum.

The projection is the Krüger series (3 terms, sub-millimeter within a zone), the same
one InOrbit's simulations use; no external dependency.
"""

import math
from typing import Tuple

# WGS84
_A = 6378137.0
_F = 1 / 298.257223563
_E2 = _F * (2 - _F)
_E = math.sqrt(_E2)
_N = _F / (2 - _F)
_RECTIFYING_RADIUS = _A / (1 + _N) * (1 + _N**2 / 4 + _N**4 / 64)
_ALPHA = (
    _N / 2 - 2 * _N**2 / 3 + 5 * _N**3 / 16,
    13 * _N**2 / 48 - 3 * _N**3 / 5,
    61 * _N**3 / 240,
)
_K0 = 0.9996
_FALSE_EASTING = 500000.0
_FALSE_NORTHING_SOUTH = 10000000.0

# Distance used to measure the local scale and rotation of the projection at the datum
_DIFF_STEP_M = 100.0


def utm_zone(longitude: float) -> int:
    """The UTM zone (1..60) of a longitude in degrees."""
    return min(int((longitude + 180) / 6) + 1, 60)


def utm_frame_id(latitude: float, longitude: float) -> str:
    """InOrbit's frame id for the UTM zone of a position: ``utm-<zone>``, and
    ``utm-<zone>-s`` south of the equator."""
    zone = utm_zone(longitude)
    return f"utm-{zone}-s" if latitude < 0 else f"utm-{zone}"


def latlon_to_utm(
    latitude: float, longitude: float, zone: int = None
) -> Tuple[float, float]:
    """Projects a WGS84 position to UTM.

    Args:
        latitude (float): degrees, -80..84.
        longitude (float): degrees.
        zone (int, optional): the zone to project to. Defaults to the position's own
            zone.

    Returns:
        Tuple[float, float]: easting and northing in meters (northing with the 10000 km
            false northing south of the equator).
    """
    if not -80.0 <= latitude <= 84.0:
        raise ValueError(f"UTM covers latitudes -80..84, not {latitude}")
    zone = zone or utm_zone(longitude)
    phi = math.radians(latitude)
    lam = math.radians(longitude - (6 * zone - 183))
    t = math.sinh(math.atanh(math.sin(phi)) - _E * math.atanh(_E * math.sin(phi)))
    xi = math.atan2(t, math.cos(lam))
    eta = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    easting, northing = eta, xi
    for j, alpha in enumerate(_ALPHA, start=1):
        easting += alpha * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
        northing += alpha * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
    easting = _FALSE_EASTING + _K0 * _RECTIFYING_RADIUS * easting
    northing = _K0 * _RECTIFYING_RADIUS * northing
    if latitude < 0:
        northing += _FALSE_NORTHING_SOUTH
    return easting, northing


class MapDatum:
    """A robot's local map frame anchored to the Earth: its origin is at (latitude,
    longitude), x points east and y north, rotated by ``yaw`` (radians,
    counterclockwise from east), as robot_localization's navsat_transform datum.

    It converts map poses to the UTM frame InOrbit draws outdoor robots in, through the
    affine map -> UTM transformation at the datum: exact at the origin, within
    centimeters over a few kilometers.
    """

    def __init__(self, latitude: float, longitude: float, yaw: float = 0.0):
        """
        Args:
            latitude (float): latitude of the map origin, degrees.
            longitude (float): longitude of the map origin, degrees.
            yaw (float, optional): angle of the map's x axis from east, radians.
                Defaults to 0 (x east, y north).
        """
        self.latitude = latitude
        self.longitude = longitude
        self.yaw = yaw
        self.frame_id = utm_frame_id(latitude, longitude)
        self._zone = utm_zone(longitude)

        # Local east and north derivatives of the projection, by central differences
        # of _DIFF_STEP_M: they hold the grid convergence and the scale factor here
        phi = math.radians(latitude)
        w = math.sqrt(1 - _E2 * math.sin(phi) ** 2)
        dlat = math.degrees(_DIFF_STEP_M / (_A * (1 - _E2) / w**3))
        dlon = math.degrees(_DIFF_STEP_M / (_A / w * math.cos(phi)))
        e_east1, n_east1 = self._utm(latitude, longitude + dlon)
        e_east0, n_east0 = self._utm(latitude, longitude - dlon)
        e_north1, n_north1 = self._utm(latitude + dlat, longitude)
        e_north0, n_north0 = self._utm(latitude - dlat, longitude)
        step = 2 * _DIFF_STEP_M
        east = ((e_east1 - e_east0) / step, (n_east1 - n_east0) / step)
        north = ((e_north1 - e_north0) / step, (n_north1 - n_north0) / step)

        # map -> local east/north (the datum yaw), then east/north -> UTM
        cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
        self._a00 = east[0] * cos_yaw + north[0] * sin_yaw
        self._a01 = -east[0] * sin_yaw + north[0] * cos_yaw
        self._a10 = east[1] * cos_yaw + north[1] * sin_yaw
        self._a11 = -east[1] * sin_yaw + north[1] * cos_yaw
        self._origin = self._utm(latitude, longitude)
        # The map's x axis direction in the UTM grid
        self._yaw_offset = math.atan2(self._a10, self._a00)

    def _utm(self, latitude, longitude):
        # Always the datum's zone, so a robot near a zone border stays in one frame
        return latlon_to_utm(latitude, longitude, self._zone)

    @property
    def transformation(self):
        """The map -> UTM transformation, as the 3x3 matrix of an InOrbit
        SpatialTransformation."""
        return [
            [self._a00, self._a01, self._origin[0]],
            [self._a10, self._a11, self._origin[1]],
            [0.0, 0.0, 1.0],
        ]

    def map_to_utm(self, x: float, y: float, yaw: float) -> Tuple[float, float, float]:
        """Converts a pose in the robot's map frame to the datum's UTM frame.

        Args:
            x (float): meters.
            y (float): meters.
            yaw (float): radians.

        Returns:
            Tuple[float, float, float]: easting, northing (meters) and yaw in the UTM
                grid (radians, counterclockwise from grid east, wrapped to -pi..pi).
        """
        easting = self._origin[0] + self._a00 * x + self._a01 * y
        northing = self._origin[1] + self._a10 * x + self._a11 * y
        utm_yaw = math.atan2(
            math.sin(yaw + self._yaw_offset), math.cos(yaw + self._yaw_offset)
        )
        return easting, northing, utm_yaw


def latlon_to_utm_pose(
    latitude: float, longitude: float, yaw: float
) -> Tuple[str, float, float, float]:
    """Converts a GPS position and heading to a pose in the UTM frame of its zone.

    Args:
        latitude (float): degrees, -80..84.
        longitude (float): degrees.
        yaw (float): radians, counterclockwise from east (ENU, as ROS).

    Returns:
        Tuple[str, float, float, float]: frame id, easting, northing (meters) and yaw in
            the UTM grid (radians, counterclockwise from grid east, wrapped to -pi..pi).
    """
    # A datum at the position itself: exact there, and it turns the heading by the grid
    # convergence
    datum = MapDatum(latitude, longitude)
    easting, northing, utm_yaw = datum.map_to_utm(0.0, 0.0, yaw)
    return datum.frame_id, easting, northing, utm_yaw
