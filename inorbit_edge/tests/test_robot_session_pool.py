#!/usr/bin/env python
# -*- coding: utf-8 -*-

from inorbit_edge.robot import RobotSessionFactory, RobotSessionPool


def test_robot_session_pool_get_session():
    factory = RobotSessionFactory(app_key="appkey_123")
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


def test_robot_session_pool_free():
    factory = RobotSessionFactory(app_key="appkey_123")
    pool = RobotSessionPool(factory)

    pool.get_session("id_1", "name_1")
    pool.get_session("id_2", "name_2")

    pool.free_robot_session("id_1")

    assert all(
        [
            not pool.has_robot("id_1"),
            pool.has_robot("id_2")
        ]
    )


def test_robot_session_pool_tear_down():
    factory = RobotSessionFactory(app_key="appkey_123")
    pool = RobotSessionPool(factory)

    pool.get_session("id_1", "name_1")
    pool.get_session("id_2", "name_2")

    pool.tear_down()

    assert all(
        [
            not pool.has_robot("id_1"),
            not pool.has_robot("id_2")
        ]
    )
