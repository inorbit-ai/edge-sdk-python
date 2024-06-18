#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import os
from typing import Optional

# Third-party
from pydantic import BaseModel, AnyUrl, field_validator, HttpUrl

# InOrbit
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL, INORBIT_REST_API_URL


class CameraConfig(BaseModel):
    """A class representing a camera configuration model.

    This class inherits from the `BaseModel` class. None values should be interpreted as
    "use the default values".

    Attributes:
        video_url (AnyUrl): The URL of the video feed from the camera
        rate (int, optional): The rate at which frames are captured from the camera
        quality (int, optional): The quality of the captured frames from the camera
        scaling (float, optional): The scaling factor for the frames from the camera
    """

    video_url: AnyUrl
    quality: Optional[int] = None
    rate: Optional[int] = None
    scaling: Optional[float] = None

    # noinspection PyMethodParameters
    @field_validator("quality")
    def check_quality_range(cls, quality: Optional[float]) -> Optional[float]:
        """Check if the quality is between 1 and 100.

        This is used for quality.

        Args:
            quality (int | None): The quality value to be checked

        Raises:
            ValueError: If the value is not between 1 and 100

        Returns:
            int | None: The given value if it is between 1 and 100, or None if the input
                        value was None
        """

        if quality is not None and not (1 <= quality <= 100):
            raise ValueError("Must be between 1 and 100")
        return quality

    # noinspection PyMethodParameters
    @field_validator("rate", "scaling")
    def check_positive(cls, value: Optional[float]) -> Optional[float]:
        """Check if an argument is positive and non-zero.

        This is used for rate and scaling values.

        Args:
            value (float | None): The value to be checked

        Raises:
            ValueError: If the value is less than or equal to zero

        Returns:
            float | None : The given value if it is positive and non-zero, or None if
                           input value was None
        """
        if value is not None and value <= 0:
            raise ValueError("Must be positive and non-zero")
        return value


class RobotSessionModel(BaseModel):
    """A class representing InOrbit robot session.

    This class inherits from the `BaseModel` class.

    The following environment variables will be read during instantiation:

    * INORBIT_API_KEY (required): The InOrbit API key
    * INORBIT_USE_SSL: If SSL should be used (default is true)
    * INORBIT_API_URL: The URL of the API (default is
        inorbit_edge.robot.INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL)
    * INORBIT_REST_API_URL: The URL of the InOrbit REST API (default is
        inorbit_edge.robot.INORBIT_REST_API_URL)

    Attributes:
        robot_id (str): The unique ID of the robot
        robot_name (str): The name of the robot
        robot_key (str | None, optional): The robot key for InOrbit cloud services
        api_key (str | None, optional): The InOrbit API token
        use_ssl (bool, optional): If SSL is used for the InOrbit API connection
        endpoint (HttpUrl, optional): The URL of the API or inorbit_edge's
                                      INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL by default
        rest_api_endpoint (HttpUrl, optional): The URL of the InOrbit REST API.
                                               INORBIT_REST_API_URL by default.
        account_id (str, optional): The account ID of the robot owner. Required for
                                    applying configurations to the robot.
    """

    robot_id: str
    robot_name: str
    robot_key: Optional[str] = None
    api_key: Optional[str] = os.getenv("INORBIT_API_KEY")
    use_ssl: bool = os.environ.get("INORBIT_USE_SSL", "true").lower() == "true"
    endpoint: HttpUrl = os.environ.get(
        "INORBIT_API_URL", INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL
    )
    rest_api_endpoint: Optional[HttpUrl] = os.environ.get(
        "INORBIT_REST_API_URL", INORBIT_REST_API_URL
    )
    account_id: Optional[str] = None

    # noinspection PyMethodParameters
    @field_validator("robot_id", "robot_name", "robot_key", "api_key", "account_id")
    def check_whitespace(cls, value: str) -> str:
        """Check if the field contains whitespace.

        This is used for the robot_id, robot_name, robot_key, and api_key.

        Args:
            value (str): The field to be checked

        Raises:
            ValueError: If the field contains whitespace

        Returns:
            str: The given value if it does not contain whitespaces
        """
        if value and any(char.isspace() for char in value):
            raise ValueError("Whitespaces are not allowed")
        return value
