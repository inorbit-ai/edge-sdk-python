#!/usr/bin/env python
# -*- coding: utf-8 -*-

from inorbit_edge.robot import RobotSession
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL
from inorbit_edge import get_module_version


def test_robot_session_init(monkeypatch):
    # test required parameters only (using api_key)
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

    # test with robot_key instead of api_key
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", robot_key="robotkey_123"
    )

    assert all(
        [
            robot_session.robot_id == "id_123",
            robot_session.robot_name == "name_123",
            robot_session.robot_key == "robotkey_123",
            robot_session.agent_version.endswith("edgesdk_py"),
            robot_session.endpoint == INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL,
            robot_session.use_ssl,
            not robot_session.use_websockets,
            robot_session.client._transport == "tcp",
            robot_session.http_proxy is None,
        ]
    )


def test_robot_session_connect(mock_mqtt_client, mock_inorbit_api):
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )
    robot_session.connect()
    # manually execute on_connect callback so robot status is sent
    robot_session._on_connect(..., ..., ..., 0)
    assert robot_session.api_key == "apikey_123"
    assert robot_session.robot_api_key == "robot_apikey_123"
    # check publish state was called with the correct API key
    robot_session.client.publish.assert_any_call(
        topic="r/id_123/state",
        payload="1|robot_apikey_123|{}.edgesdk_py|name_123".format(
            get_module_version()
        ),
        qos=1,
        retain=True,
    )
    # check resend modules is called
    robot_session.client.publish.assert_any_call(
        topic="r/id_123/out_cmd",
        payload="resend_modules",
        qos=1,
        retain=False,
    )


def test_method_throttling():
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )

    assert robot_session._should_publish_message(method="publish_pose")
    assert not robot_session._should_publish_message(method="publish_pose")
    assert not robot_session._should_publish_message(method="publish_pose")
    robot_session._publish_throttling["publish_pose"]["last_ts"] = 0
    assert robot_session._should_publish_message(method="publish_pose")

    # Also test key based throttling
    assert robot_session._should_publish_message(method="publish_key_values", key="foo")
    assert not robot_session._should_publish_message(
        method="publish_key_values", key="foo"
    )
    robot_session._publish_throttling["publish_key_values"]["foo"]["last_ts"] = 0
    assert robot_session._should_publish_message(method="publish_key_values", key="foo")

    assert robot_session._should_publish_message(method="publish_key_values", key="bar")
    assert not robot_session._should_publish_message(
        method="publish_key_values", key="bar"
    )
    robot_session._publish_throttling["publish_key_values"]["bar"]["last_ts"] = 0
    assert robot_session._should_publish_message(method="publish_key_values", key="bar")
