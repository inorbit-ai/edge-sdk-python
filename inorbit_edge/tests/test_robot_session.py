#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytest
from inorbit_edge.robot import RobotSession
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL


@pytest.mark.parametrize(
    "robot_id, robot_name, app_key",
    [
        # (robot_id, robot_name, app_key)
        ("abc123", "R2D2", "s3cr3t")
    ],
)
def test_foo(robot_id, robot_name, app_key):
    robot_session = RobotSession(robot_id, robot_name, app_key)
    assert robot_session.robot_id == robot_id
    assert robot_session.robot_name == robot_name
    assert robot_session.app_key == app_key


def test_robot_session_init(monkeypatch):
    # test required parameters only
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", app_key="appkey_123"
    )

    assert all(
        [
            robot_session.robot_id == "id_123",
            robot_session.robot_name == "name_123",
            robot_session.app_key == "appkey_123",
            robot_session.agent_version.endswith("edgesdk_py"),
            robot_session.endpoint == INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL,
            robot_session.use_ssl,
            not robot_session.use_websocket,
            robot_session.client._transport == "tcp",
            robot_session.http_proxy is None,
        ]
    )

    # test proxy environment variable
    with monkeypatch.context() as m:
        m.setenv("HTTP_PROXY", "http://foo_bar.com:1234")
        robot_session = RobotSession(
            robot_id="id_123", robot_name="name_123", app_key="appkey_123"
        )

        assert all(
            [
                robot_session.use_websocket,
                robot_session.client._transport == "websockets",
                robot_session.http_proxy == "http://foo_bar.com:1234",
            ]
        )
