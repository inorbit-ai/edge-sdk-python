#!/usr/bin/env python
# -*- coding: utf-8 -*-

from inorbit_edge.robot import RobotSessionFactory


def test_robot_factory_build():
    robot_session_factory = RobotSessionFactory(app_key="appkey_123",
                                                endpoint="http://myendpoint/")
    robot_session = robot_session_factory.build("id_123", "name_123")

    assert all(
        [
            robot_session.robot_id == "id_123",
            robot_session.robot_name == "name_123",
            robot_session.app_key == "appkey_123",
            robot_session.agent_version.endswith("edgesdk_py"),
            robot_session.endpoint == "http://myendpoint/",
            robot_session.use_ssl,
            not robot_session.use_websocket,
            robot_session.client._transport == "tcp",
            robot_session.http_proxy is None,
        ]
    )
