#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Unit tests for checking the proper functioning of the
fetch_robot_config function from robot.py
NOTE: All test file names must have one of the two forms.
- `test_<XYY>.py`
- '<XYZ>_test.py'

Docs: https://docs.pytest.org/en/latest/
      https://docs.pytest.org/en/latest/goodpractices.html#conventions-for-python-test-discovery
"""

from inorbit_edge.robot import RobotSession
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL
import requests_mock
import pytest

# Dummy database sample for testing
DATABASE = {
    "hostname": "localdev.com",
    "port": 1883,
    "protocol": "mqtt://",
    "websocket_port": 9001,
    "websocket_protocol": "ws://",
    "username": "test",
    "password": "mytest123",
    "robotApiKey": "appkey_123",
    "awsUploadCredentials": {
        "secretKey": "secret_key",
        "accessKey": "access_key",
        "company": "fakecompany",
        "bucket": "inorbit-data-other",
    },
}


# path where the robot session can fetch the robot config properly
def test_get_robot_config_from_session():
    # test required parameters only
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="appkey_123"
    )

    with requests_mock.Mocker() as mock:
        mock.post(INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL, json=DATABASE)
        robot_config = robot_session._fetch_robot_config()

        assert robot_config is not None

        assert all(
            [
                robot_config["hostname"] == "localdev.com",
                robot_config["port"] == 1883,
                robot_config["protocol"] == "mqtt://",
                robot_config["websocket_port"] == 9001,
                robot_config["websocket_protocol"] == "ws://",
                robot_config["username"] == "test",
                robot_config["password"] == "mytest123",
                robot_config["robotApiKey"] == "appkey_123",
                robot_config["awsUploadCredentials"] is not None,
            ]
        )


# path where the robot session cannot fetch the robot config properly
def test_bad_request_error():
    # test required parameters only
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="appkey_123"
    )

    with requests_mock.Mocker() as mock:
        mock.post(INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL, status_code=500)

        with pytest.raises(Exception):
            robot_session._fetch_robot_config()
