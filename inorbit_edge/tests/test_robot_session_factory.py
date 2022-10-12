#!/usr/bin/env python
# -*- coding: utf-8 -*-

from inorbit_edge.robot import RobotSessionFactory


def test_robot_factory_build(mock_mqtt_client):
    robot_session_factory = RobotSessionFactory(
        api_key="apikey_123", endpoint="http://myendpoint/"
    )
    robot_session = robot_session_factory.build("id_123", "name_123")

    assert all(
        [
            robot_session.robot_id == "id_123",
            robot_session.robot_name == "name_123",
            robot_session.api_key == "apikey_123",
            robot_session.agent_version.endswith("edgesdk_py"),
            robot_session.endpoint == "http://myendpoint/",
            robot_session.http_proxy is None,
        ]
    )
