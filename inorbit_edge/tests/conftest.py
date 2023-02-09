#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Configuration for tests! There are a whole list of hooks you can define in this file to
run before, after, or to mutate how tests run. Commonly for most of our work, we use
this file to define top level fixtures that may be needed for tests throughout multiple
test files.

In this case, while we aren't using this fixture in our tests, the prime use case for
something like this would be when we want to preload a file to be used in multiple
tests. File reading can take time, so instead of re-reading the file for each test,
read the file once then use the loaded content.

Docs: https://docs.pytest.org/en/latest/example/simple.html
      https://docs.pytest.org/en/latest/plugins.html#requiring-loading-plugins-in-a-test-module-or-conftest-file
"""

import pytest
import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTTMessageInfo
import requests_mock

from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL


@pytest.fixture
def mock_mqtt_client(mocker):
    fake_mid = 52
    mock = mocker.patch.object(mqtt, "Client")
    mock_mqtt_client = mock.return_value

    # Patch MQTTMessageInfo method wait_for_publish
    mock_wait_for_publish = mocker.patch.object(MQTTMessageInfo, "wait_for_publish")
    mock_wait_for_publish.return_value = True

    mqtt_message_info = MQTTMessageInfo(fake_mid)
    mock_mqtt_client.subscribe = mocker.MagicMock(return_value=mqtt_message_info)
    mock_mqtt_client.unsubscribe = mocker.MagicMock(return_value=mqtt_message_info)
    mock_mqtt_client.publish = mocker.MagicMock(return_value=mqtt_message_info)
    mock_mqtt_client.connect.return_value = 0
    mock_mqtt_client.reconnect.return_value = 0
    mock_mqtt_client.disconnect.return_value = 0
    return mock_mqtt_client


@pytest.fixture
def mock_popen(mocker):
    return mocker.patch("subprocess.Popen")


@pytest.fixture
def mock_inorbit_api():
    # Dummy cloud_sdk_robot_config sample response for testing
    ROBOT_CONFIG_MOCK_RESPONSE = {
        "hostname": "localdev.com",
        "port": 1883,
        "protocol": "mqtt://",
        "websocket_port": 9001,
        "websocket_protocol": "ws://",
        "username": "test",
        "password": "mytest123",
        "robotApiKey": "robot_apikey_123",
        "awsUploadCredentials": {
            "secretKey": "secret_key",
            "accessKey": "access_key",
            "company": "fakecompany",
            "bucket": "inorbit-data-other",
        },
    }
    with requests_mock.Mocker() as mock:
        mock.post(INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL, json=ROBOT_CONFIG_MOCK_RESPONSE)
        yield
