#!/usr/bin/env python
# -*- coding: utf-8 -*-

from inorbit_edge.robot import RobotSessionFactory, RobotSessionPool


def test_robot_session_pool_get_session(mock_mqtt_client, mock_inorbit_api):
    factory = RobotSessionFactory(api_key="apikey_123")
    pool = RobotSessionPool(factory)

    robot1 = pool.get_session("id_1", "name_1")
    robot1_copy = pool.get_session("id_1", "name_1")
    robot2 = pool.get_session("id_2", "name_2")

    assert all(
        [
            robot1.robot_id == "id_1",
            robot1.robot_name == "name_1",
            robot1 is not robot2,
            robot1 is robot1_copy,
        ]
    )


def test_robot_session_pool_free(mock_mqtt_client, mock_inorbit_api):
    factory = RobotSessionFactory(api_key="apikey_123")
    pool = RobotSessionPool(factory)

    sess1 = pool.get_session("id_1", "name_1")
    sess1._is_disconnected = lambda: True

    sess2 = pool.get_session("id_2", "name_2")
    sess2._is_disconnected = lambda: True

    pool.free_robot_session("id_1")

    assert all([not pool.has_robot("id_1"), pool.has_robot("id_2")])


def test_robot_session_pool_tear_down(mock_mqtt_client, mock_inorbit_api):
    factory = RobotSessionFactory(api_key="apikey_123")
    pool = RobotSessionPool(factory)

    sess1 = pool.get_session("id_1", "name_1")
    sess1._is_disconnected = lambda: True
    sess2 = pool.get_session("id_2", "name_2")
    sess2._is_disconnected = lambda: True

    pool.tear_down()

    assert all([not pool.has_robot("id_1"), not pool.has_robot("id_2")])
