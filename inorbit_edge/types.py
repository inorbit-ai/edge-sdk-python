from dataclasses import dataclass


@dataclass
class Pose:
    frame_id: str
    x: float
    y: float
    theta: float


@dataclass
class SpatialTolerance:
    positionMeters: float
    angularRadians: float
