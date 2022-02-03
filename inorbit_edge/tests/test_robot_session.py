#!/usr/bin/env python
# -*- coding: utf-8 -*-

from unittest.mock import MagicMock
from inorbit_edge.robot import RobotSession
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL
from inorbit_edge.tests.test_fetch_robot_config import ROBOT_CONFIG_MOCK_RESPONSE
from inorbit_edge import get_module_version
import requests_mock


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
        # manually execute on_connect callback to send robot status
        robot_session.send_robot_status("1")
        assert robot_session.api_key == "apikey_123"
        assert robot_session.robot_api_key == "robot_apikey_123"
        # check publish state was called with the correct API key
        publish_mock.assert_called_with(
            "r/id_123/state",
            "1|robot_apikey_123|{}.edgesdk_py|name_123".format(get_module_version()),
            qos=1,
            retain=True,
        )
