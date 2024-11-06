#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import pytest
from requests import HTTPError

from inorbit_edge.robot import RobotSession, RobotFootprintSpec
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL, INORBIT_REST_API_URL
from inorbit_edge import get_module_version
from inorbit_edge.inorbit_pb2 import MapMessage


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
    # noinspection PyArgumentList
    with monkeypatch.context() as m:
        m.setenv("HTTP_PROXY", "https://foo_bar.com:1234")
        robot_session = RobotSession(
            robot_id="id_123", robot_name="name_123", api_key="apikey_123"
        )

        assert all(
            [
                robot_session.use_websockets,
                robot_session.client._transport == "websockets",
                robot_session.http_proxy == "https://foo_bar.com:1234",
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


def test_apply_footprint(requests_mock):
    adapter = requests_mock.post(
        f"{INORBIT_REST_API_URL}/configuration/apply",
        json={"operationStatus": "SUCCESS"},
    )
    footprint = RobotFootprintSpec(
        footprint=[
            {"x": -0.5, "y": -0.5},
            {"x": 0.3, "y": -0.5},
            {"x": 0.3, "y": 0.5},
            {"x": -0.5, "y": 0.5},
        ],
        radius=0.2,
    )

    # Missing account_id
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    with pytest.raises(ValueError):
        robot_session.apply_footprint(footprint)

    # Successful request
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
        account_id="account_123",
    )
    robot_session.apply_footprint(footprint)
    assert adapter.called_once
    assert adapter.last_request.json() == {
        "apiVersion": "v0.1",
        "kind": "RobotFootprint",
        "metadata": {
            "id": "all",
            "scope": "robot/account_123/id_123",
        },
        "spec": {
            "footprint": [
                {"x": -0.5, "y": -0.5},
                {"x": 0.3, "y": -0.5},
                {"x": 0.3, "y": 0.5},
                {"x": -0.5, "y": 0.5},
            ],
            "radius": 0.2,
        },
    }

    # HTTP error
    requests_mock.post(f"{INORBIT_REST_API_URL}/configuration/apply", status_code=400)
    with pytest.raises(HTTPError):
        robot_session.apply_footprint(footprint)


def test_robot_session_publishes_map_data(
    mock_mqtt_client, mock_inorbit_api, mock_popen
):
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )

    # Test with bad file
    robot_session.publish_map(
        file="you/are/not/going/to/find.me",
        map_id="map_id",
        frame_id="frame_id",
        x=1,
        y=2,
        resolution=0.005,
        ts=123,
        is_update=False,
        force_upload=False,
    )
    robot_session.client.publish.assert_not_called()

    # Tets without force_upload
    robot_session.publish_map(
        file=f"{os.path.dirname(__file__)}/utils/test_map.png",
        map_id="map_id",
        frame_id="frame_id",
        x=1,
        y=2,
        resolution=0.005,
        ts=123,
        is_update=False,
        force_upload=False,
    )

    expected_payload = MapMessage()
    expected_payload.width = 4
    expected_payload.height = 4
    expected_payload.data_hash = 4565286020005755223
    expected_payload.label = "map_id"
    expected_payload.map_id = "map_id"
    expected_payload.frame_id = "frame_id"
    expected_payload.x = 1
    expected_payload.y = 2
    expected_payload.resolution = 0.005
    expected_payload.ts = 123
    expected_payload.is_update = False

    robot_session.client.publish.assert_any_call(
        topic="r/id_123/ros/loc/map2",
        payload=bytearray(expected_payload.SerializeToString()),
        qos=1,
        retain=True,
    )

    # Test with force_upload
    robot_session.publish_map(
        file=f"{os.path.dirname(__file__)}/utils/test_map.png",
        map_id="map_id",
        frame_id="frame_id",
        x=1,
        y=2,
        resolution=0.005,
        ts=123,
        is_update=False,
        force_upload=True,
    )

    expected_payload = MapMessage()
    expected_payload.width = 4
    expected_payload.height = 4
    expected_payload.data_hash = 4565286020005755223
    expected_payload.label = "map_id"
    expected_payload.map_id = "map_id"
    expected_payload.frame_id = "frame_id"
    expected_payload.x = 1
    expected_payload.y = 2
    expected_payload.resolution = 0.005
    expected_payload.ts = 123
    expected_payload.is_update = False
    expected_payload.pixels = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x04\x00\x00\x00\x04\x08\x02\x00\x00\x00&\x93\t)\x00\x00\x01\x84iCCPICC Profile\x00\x00x\x9c}\x91=H\xc3@\x1c\xc5_S\xb5\xa2-\x0ev\x10q\x88P\x9d,\x88\x8a8j\x15\x8aP!\xd4\n\xad:\x98\\\xfa\x05M\x1a\x92\x14\x17G\xc1\xb5\xe0\xe0\xc7b\xd5\xc1\xc5YW\x07WA\x10\xfc\x00qvpRt\x91\x12\xff\xd7\x14Z\xc4xp\xdc\x8fw\xf7\x1ew\xef\x00\xa1Vb\x9a\xd51\x0eh\xbam&\xe311\x9dY\x15\x03\xaf\xe8E\x17B\x18\xc6\xb4\xcc,cN\x92\x12\xf0\x1c_\xf7\xf0\xf1\xf5.\xca\xb3\xbc\xcf\xfd9Bj\xd6b\x80O$\x9ee\x86i\x13o\x10Oo\xda\x06\xe7}\xe20+\xc8*\xf19\xf1\x98I\x17$~\xe4\xba\xe2\xf2\x1b\xe7|\x83\x05\x9e\x196S\xc9y\xe20\xb1\x98oc\xa5\x8dY\xc1\xd4\x88\xa7\x88#\xaa\xa6S\xbe\x90vY\xe5\xbc\xc5Y+UX\xf3\x9e\xfc\x85\xc1\xac\xbe\xb2\xccu\x9aC\x88c\x11K\x90 BA\x05E\x94`#J\xabN\x8a\x85$\xed\xc7<\xfc\x83\r\xbfD.\x85\\E0r,\xa0\x0c\rr\xc3\x0f\xfe\x07\xbf\xbb\xb5r\x93\x13nR0\x06t\xbe8\xce\xc7\x08\x10\xd8\x05\xeaU\xc7\xf9>v\x9c\xfa\t\xe0\x7f\x06\xae\xf4\x96\xbf\\\x03f>I\xaf\xb6\xb4\xc8\x11\xd0\xb7\r\\\\\xb74e\x0f\xb8\xdc\x01\x06\x9e\x0c\xd9\x94\x1b\x92\x9f\xa6\x90\xcb\x01\xefg\xf4M\x19\xa0\xff\x16\xe8Ys{k\xee\xe3\xf4\x01HQW\x89\x1b\xe0\xe0\x10\x18\xcdS\xf6\xba\xc7\xbb\xbb\xdb{\xfb\xf7L\xb3\xbf\x1f\x98Nr\xb6\xd8\x8a\xb30\x00\x00\x00\x14IDATx\x9cc\xfc\xff\xff?\x03\x0c01 \x01\xdc\x1c\x00\x96n\x03\x05\xf2%\xbe\xf9\x00\x00\x00\x00IEND\xaeB`\x82"  # noqa E501

    robot_session.client.publish.assert_any_call(
        topic="r/id_123/ros/loc/map2",
        payload=bytearray(expected_payload.SerializeToString()),
        qos=1,
        retain=True,
    )
