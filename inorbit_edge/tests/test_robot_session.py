#!/usr/bin/env python
# -*- coding: utf-8 -*-

from unittest.mock import MagicMock
from inorbit_edge.robot import RobotSession
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL
from inorbit_edge.tests.test_fetch_robot_config import ROBOT_CONFIG_MOCK_RESPONSE
from inorbit_edge import get_module_version
import requests_mock
import pytest
import logging
from paho.mqtt.client import MQTTMessage


def test_robot_session_init(monkeypatch):
    # test required parameters only
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )

    assert all(
        [
            robot_session.robot_id == "id_123",
            robot_session.robot_name == "name_123",
            robot_session.api_key == "apikey_123",
            robot_session.agent_version.endswith("edgesdk_py"),
            robot_session.endpoint == INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL,
            robot_session.use_ssl,
            not robot_session.use_websockets,
            robot_session.client._transport == "tcp",
            robot_session.http_proxy is None,
        ]
    )

    # test proxy environment variable
    with monkeypatch.context() as m:
        m.setenv("HTTP_PROXY", "http://foo_bar.com:1234")
        robot_session = RobotSession(
            robot_id="id_123", robot_name="name_123", api_key="apikey_123"
        )

        assert all(
            [
                robot_session.use_websockets,
                robot_session.client._transport == "websockets",
                robot_session.http_proxy == "http://foo_bar.com:1234",
            ]
        )


def test_robot_session_connect(monkeypatch):
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )

    with requests_mock.Mocker() as mock:
        mock.post(INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL, json=ROBOT_CONFIG_MOCK_RESPONSE)
        # mock mqtt client
        monkeypatch.setattr(robot_session, "client", MagicMock())
        # mock publish and is_published so it always returns True
        is_published_mock = MagicMock()
        is_published_mock.is_published.return_value = True
        publish_mock = MagicMock(return_value=is_published_mock)
        monkeypatch.setattr(robot_session, "publish", publish_mock)
        # connect robot_session so it populates properties with API response data
        robot_session.connect()
        # manually execute send_robot_status simulating on_connect
        # callback execution so robot status is sent
        robot_session._send_robot_status("1")
        assert robot_session.api_key == "apikey_123"
        assert robot_session.robot_api_key == "robot_apikey_123"
        # check publish state was called with the correct API key
        publish_mock.assert_called_with(
            "r/id_123/state",
            "1|robot_apikey_123|{}.edgesdk_py|name_123".format(get_module_version()),
            qos=1,
            retain=True,
        )


def test_robot_session_custom_command_callback(monkeypatch):
    def my_custom_command_handler(robot_session, msg):
        pass

    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
        custom_command_callback=my_custom_command_handler,
    )

    with requests_mock.Mocker() as mock:
        mock.post(INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL, json=ROBOT_CONFIG_MOCK_RESPONSE)
        # mock mqtt client
        mqtt_client_mock = MagicMock()
        mqtt_client_mock.subscribe.return_value = (0, 0)
        monkeypatch.setattr(robot_session, "client", mqtt_client_mock)
        # mock publish and is_published so it always returns True
        is_published_mock = MagicMock()
        is_published_mock.is_published.return_value = True
        publish_mock = MagicMock(return_value=is_published_mock)
        monkeypatch.setattr(robot_session, "publish", publish_mock)
        # connect robot_session so it populates properties with API response data
        robot_session.connect()
        # manually execute on_connect callback so the ``custom_command_callback``
        # callback gets registered
        robot_session._on_connect(..., ..., ..., 0)

        assert robot_session.custom_command_callback == my_custom_command_handler
        mqtt_client_mock.subscribe.assert_called_with(topic="r/id_123/custom_command")


@pytest.mark.parametrize(
    "msg_payload, log_string",
    [
        (b"\x8f\xac\x93\x87 \x8fG\x95v", "Failed to decode message, ignoring."),
        (b'{"msg":"foobar"}}}}}}}', "Failed to parse JSON message, ignoring."),
    ],
)
def test_robot_session_on_message_callback(caplog, msg_payload, log_string):
    def my_custom_command_handler(robot_session, msg):
        pass

    with caplog.at_level(logging.ERROR, logger=RobotSession.__name__):
        robot_session = RobotSession(
            robot_id="id_123",
            robot_name="name_123",
            api_key="apikey_123",
            custom_command_callback=my_custom_command_handler,
        )

        mqtt_message = MQTTMessage(topic=b"/foo")
        mqtt_message.payload = msg_payload

        robot_session._on_message(..., ..., mqtt_message)
        assert log_string in caplog.text
