#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import os
from unittest.mock import MagicMock
import pytest
from requests import HTTPError

from inorbit_edge.robot import RobotSession, RobotFootprintSpec, RobotMap
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL, INORBIT_REST_API_URL
from inorbit_edge import get_module_version
from inorbit_edge.inorbit_pb2 import MapMessage, RobotPath, PathDataMessage, PathPoint


def test_robot_session_init(monkeypatch, mock_sleep):
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


def test_robot_session_connect(mock_mqtt_client, mock_inorbit_api, mock_sleep):
    robot_session = RobotSession(
        robot_id="id_123", robot_name="name_123", api_key="apikey_123"
    )
    robot_session.connect()
    # manually execute on_connect callback so robot status is sent
    robot_session._on_connect(None, None, None, 0, None)
    assert robot_session.api_key == "apikey_123"
    assert robot_session.robot_api_key == "robot_apikey_123"
    # check publish state was called with the correct API key
    robot_session.client.publish.assert_any_call(
        "r/id_123/state",
        "1|robot_apikey_123|{}.edgesdk_py|name_123".format(get_module_version()),
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


def test_method_throttling(mock_sleep):
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


def test_apply_footprint(requests_mock, mock_sleep):
    requests_mock.get(
        f"{INORBIT_REST_API_URL}/user",
        json={"userId": "user_abc", "name": "Test User", "accountIds": ["account_123"]},
    )
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

    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
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

    # HTTP error on apply
    requests_mock.post(f"{INORBIT_REST_API_URL}/configuration/apply", status_code=400)
    with pytest.raises(HTTPError):
        robot_session.apply_footprint(footprint)


def test_get_account_id(requests_mock, mock_sleep):
    requests_mock.get(
        f"{INORBIT_REST_API_URL}/user",
        json={"userId": "user_abc", "name": "Test User", "accountIds": ["account_123"]},
    )
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    assert robot_session.get_account_id() == "account_123"
    # Second call uses cache -- no extra HTTP request
    assert robot_session.get_account_id() == "account_123"
    user_requests = [h for h in requests_mock.request_history if "/user" in h.path]
    assert len(user_requests) == 1


def test_get_account_id_no_api_key(mock_sleep):
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        robot_key="robotkey_123",
    )
    with pytest.raises(ValueError, match="api_key is required"):
        robot_session.get_account_id()


def test_get_account_id_empty_accounts(requests_mock, mock_sleep):
    requests_mock.get(
        f"{INORBIT_REST_API_URL}/user",
        json={"userId": "user_abc", "name": "Test User", "accountIds": []},
    )
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    with pytest.raises(ValueError, match="No account IDs found"):
        robot_session.get_account_id()


def test_get_account_id_multiple_accounts(requests_mock, mock_sleep):
    requests_mock.get(
        f"{INORBIT_REST_API_URL}/user",
        json={"userId": "user_abc", "name": "Test", "accountIds": ["a1", "a2"]},
    )
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    with pytest.raises(ValueError, match="Multiple account IDs"):
        robot_session.get_account_id()


def test_get_account_id_api_error(requests_mock, mock_sleep):
    requests_mock.get(f"{INORBIT_REST_API_URL}/user", status_code=401)
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    with pytest.raises(HTTPError):
        robot_session.get_account_id()


def test_robot_map_data():
    # Test with good file
    robot_map = RobotMap(
        file=f"{os.path.dirname(__file__)}/utils/test_map.png",
        map_id="map_id",
        frame_id="frame_id",
        origin_x=1,
        origin_y=2,
        resolution=0.005,
    )
    pixels, hash, dimensions = robot_map.get_image_data()
    assert hash == 2480156625
    assert dimensions == (4, 4)
    assert pixels.startswith(b"\x89PNG\r\n")

    # Test with bad file
    robot_map = RobotMap(
        file="you/are/not/going/to/find.me",
        map_id="map_id",
        frame_id="frame_id",
        origin_x=1,
        origin_y=2,
        resolution=0.005,
    )
    with pytest.raises(FileNotFoundError):
        robot_map.get_image_data()

    # Test cache invalidation
    robot_map = RobotMap(
        file=f"{os.path.dirname(__file__)}/utils/test_map.png",
        map_id="map_id",
        frame_id="frame_id",
        origin_x=1,
        origin_y=2,
        resolution=0.005,
    )
    pixels, hash, dimensions = robot_map.get_image_data()
    robot_map._refresh_data = MagicMock()
    # File was not updated. Should not refresh data
    pixels, hash, dimensions = robot_map.get_image_data()
    robot_map._refresh_data.assert_not_called()
    # Update the file's modification time
    os.utime(robot_map.file, None)
    pixels, hash, dimensions = robot_map.get_image_data()
    robot_map._refresh_data.assert_called_once()


def test_robot_session_publishes_map_data(
    mock_mqtt_client, mock_inorbit_api, mock_popen, mock_sleep
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

    # Test without force_upload and without map_label (should default to map_id)
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
    expected_payload.data_hash = 2480156625
    expected_payload.label = "map_id"  # Should default to map_id when map_label is None
    expected_payload.map_id = "map_id"
    expected_payload.frame_id = "frame_id"
    expected_payload.x = 1
    expected_payload.y = 2
    expected_payload.resolution = 0.005
    expected_payload.ts = 123
    expected_payload.is_update = False
    expected_payload.formatVersion = 2

    robot_session.client.publish.assert_any_call(
        topic="r/id_123/ros/loc/map2",
        payload=bytearray(expected_payload.SerializeToString()),
        qos=1,
        retain=True,
    )
    assert len(robot_session.map_files) == 1
    assert robot_session.map_files.get("map_id") is not None

    # Test with force_upload and explicit map_label
    robot_session.publish_map(
        file=f"{os.path.dirname(__file__)}/utils/test_map.png",
        map_id="map_id",
        map_label="Custom Map Label",
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
    expected_payload.data_hash = 2480156625
    expected_payload.label = "Custom Map Label"  # Should use explicit map_label
    expected_payload.map_id = "map_id"
    expected_payload.frame_id = "frame_id"
    expected_payload.x = 1
    expected_payload.y = 2
    expected_payload.resolution = 0.005
    expected_payload.ts = 123
    expected_payload.is_update = False
    _test_map_pixels, _, _ = RobotMap(
        file=f"{os.path.dirname(__file__)}/utils/test_map.png",
        map_id="map_id",
        frame_id="frame_id",
        origin_x=1,
        origin_y=2,
        resolution=0.005,
    ).get_image_data()
    expected_payload.pixels = _test_map_pixels
    expected_payload.formatVersion = 2

    robot_session.client.publish.assert_any_call(
        topic="r/id_123/ros/loc/map2",
        payload=bytearray(expected_payload.SerializeToString()),
        qos=1,
        retain=True,
    )
    assert len(robot_session.map_files) == 2
    assert robot_session.map_files.get("Custom Map Label") is not None


def test_robot_session_publishes_path_data(
    mock_mqtt_client, mock_inorbit_api, mock_sleep
):
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    # Publishes a simple path with 3 points
    path_points = [
        (1, 2),
        (3, 4),
        (5, 6),
    ]
    robot_session.publish_path(path_points, ts=1)
    robot_path = RobotPath()
    robot_path.ts = 1
    robot_path.path_id = "0"
    robot_path.frame_id = "map"
    robot_path.points.extend(
        [
            PathPoint(x=1, y=2),
            PathPoint(x=3, y=4),
            PathPoint(x=5, y=6),
        ]
    )
    expected_payload = PathDataMessage()
    expected_payload.ts = 1
    expected_payload.paths.append(robot_path)
    robot_session.client.publish.assert_any_call(
        topic="r/id_123/ros/loc/path",
        payload=bytearray(expected_payload.SerializeToString()),
        qos=0,
        retain=False,
    )
    robot_session.client.reset_mock()
    # Reset throttling state
    robot_session._publish_throttling["publish_path"]["last_ts"] = 0

    # Publishes a path with 2000 points
    # The path should be simplified to a maximum of 1000 points
    path_points = [(math.sin(i), math.cos(i)) for i in range(2000)]
    robot_session.publish_path(path_points, ts=1)

    robot_session.client.publish.assert_called_once()

    call_kwargs = robot_session.client.publish.call_args[1]
    assert call_kwargs["qos"] == 0
    assert call_kwargs["retain"] is False

    path_data_message = PathDataMessage()
    path_data_message.ParseFromString(call_kwargs["payload"])

    decoded_points = [(point.x, point.y) for point in path_data_message.paths[0].points]
    assert len(decoded_points) <= 1000
    assert all(isinstance(point, tuple) and len(point) == 2 for point in decoded_points)
    assert all(
        isinstance(coord, (int, float)) for point in decoded_points for coord in point
    )


def test_robot_session_publishes_path_data_only_if_changed(
    mock_mqtt_client, mock_inorbit_api, mock_sleep
):
    robot_session = RobotSession(
        robot_id="id_123",
        robot_name="name_123",
        api_key="apikey_123",
    )
    # Publishes a simple path with 3 points
    path_points = [
        (1, 2),
        (3, 4),
        (5, 6),
    ]
    robot_session.publish_path(path_points, ts=1)

    # Reset throttling state
    robot_session._publish_throttling["publish_path"]["last_ts"] = 0

    robot_session.publish_path(path_points, ts=1)
    robot_session.client.publish.assert_called_once()
