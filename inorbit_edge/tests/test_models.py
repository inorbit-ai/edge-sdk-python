#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import importlib
import os
import re
import sys
from unittest import mock

# Third-party
import pytest
from pydantic import ValidationError

# InOrbit
from inorbit_edge.models import RobotSessionModel, CameraConfig
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL


class TestCameraConfig:
    def test_quality_validation(self):
        # Test with valid quality parameter
        camera1 = CameraConfig(video_url="https://test.com/", quality=50)
        assert camera1.quality == 50

        # Test with None quality parameter
        camera2 = CameraConfig(video_url="https://test.com/", quality=None)
        assert camera2.quality is None

        # Test outside range quality parameter
        with pytest.raises(ValueError, match="Must be between 1 and 100"):
            CameraConfig(video_url="https://test.com/", quality=-10)

        with pytest.raises(ValueError, match="Must be between 1 and 100"):
            CameraConfig(video_url="https://test.com/", quality=150)

    def test_rate_validation(self):
        # Test with valid rate parameter
        camera1 = CameraConfig(video_url="https://test.com/", rate=2)
        assert camera1.rate == 2

        # Test with None rate parameter
        camera2 = CameraConfig(video_url="https://test.com/", rate=None)
        assert camera2.rate is None

        # Test with non-positive rate parameter
        with pytest.raises(ValueError, match="Must be positive and non-zero"):
            CameraConfig(video_url="https://test.com/", rate=0)

    def test_scaling_validation(self):
        # Test with valid scaling parameter
        camera3 = CameraConfig(video_url="https://test.com/", scaling=1.5)
        assert camera3.scaling == 1.5

        # Test with None scaling parameter
        camera4 = CameraConfig(video_url="https://test.com/", scaling=None)
        assert camera4.scaling is None

        # Test with negative scaling parameter
        with pytest.raises(ValueError, match="Must be positive and non-zero"):
            CameraConfig(video_url="https://test.com/", scaling=-1.5)

    def test_video_url_validation(self):
        # Test missing URL
        error = (
            "1 validation error for CameraConfig\nvideo_url\n  Field required "
            "[type=missing, input_value={}, input_type=dict]"
        )
        with pytest.raises(ValidationError, match=re.escape(error)):
            CameraConfig()

        # Test invalid URL
        error = (
            "1 validation error for CameraConfig\nvideo_url\n  Input should be a "
            "valid URL, relative URL without a base [type=url_parsing, "
            "input_value='invalid_video_url', input_type=str]"
        )
        with pytest.raises(ValidationError, match=re.escape(error)):
            CameraConfig(video_url="invalid_video_url")

        # Test valid URL
        camera = CameraConfig(video_url="https://test.com/")
        assert str(camera.video_url) == "https://test.com/"


class TestRobotSessionModel:

    @pytest.fixture
    def base_model(self):
        return {
            "robot_id": "123",
            "robot_name": "test_robot",
            "robot_key": "valid_robot_key",
            "api_key": "valid_api_key",
        }

    def test_model_creation(self, base_model):
        model = RobotSessionModel(**base_model)
        assert model.robot_id == base_model["robot_id"]
        assert model.robot_name == base_model["robot_name"]
        assert model.robot_key == base_model["robot_key"]
        assert model.api_key == base_model["api_key"]
        assert model.use_ssl is True
        assert str(model.endpoint) == INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL

    def test_whitespace_validation_robot_id(self, base_model):
        base_model["robot_id"] = "123 "
        with pytest.raises(ValidationError, match=r"Whitespaces are not allowed"):
            RobotSessionModel(**base_model)

    def test_whitespace_validation_robot_name(self, base_model):
        base_model["robot_name"] = "test robot"
        with pytest.raises(ValidationError, match=r"Whitespaces are not allowed"):
            RobotSessionModel(**base_model)

    def test_whitespace_validation_robot_key(self, base_model):
        base_model["robot_key"] = "abc def"
        with pytest.raises(ValidationError, match=r"Whitespaces are not allowed"):
            RobotSessionModel(**base_model)

    def test_whitespace_validation_api_key(self, base_model):
        base_model["api_key"] = "abc def"
        with pytest.raises(ValidationError, match=r"Whitespaces are not allowed"):
            RobotSessionModel(**base_model)

    def test_whitespace_validation_account_id(self, base_model):
        base_model["account_id"] = "abc def"
        with pytest.raises(ValidationError, match=r"Whitespaces are not allowed"):
            RobotSessionModel(**base_model)

    @mock.patch.dict(os.environ, {"INORBIT_API_KEY": "env_valid_key"})
    def test_reads_api_key_from_environment_variable(self, base_model):
        # Re-import after Mock
        importlib.reload(sys.modules["inorbit_edge.models"])
        from inorbit_edge.models import RobotSessionModel

        init_input = {
            "robot_id": "123",
            "robot_name": "test_robot",
            "robot_key": "valid_robot_key",
        }
        model = RobotSessionModel(**init_input)
        assert model.api_key == "env_valid_key"

    @mock.patch.dict(os.environ, {"INORBIT_USE_SSL": "false"})
    def test_reads_use_ssl_from_environment_variable(self, base_model):
        # Re-import after Mock
        importlib.reload(sys.modules["inorbit_edge.models"])
        from inorbit_edge.models import RobotSessionModel

        init_input = {
            "robot_id": "123",
            "robot_name": "test_robot",
            "robot_key": "valid_robot_key",
        }
        model = RobotSessionModel(**init_input)
        assert model.use_ssl is False
