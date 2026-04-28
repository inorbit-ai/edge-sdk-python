# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
# SPDX-License-Identifier: MIT

import asyncio
import warnings

import pytest

from inorbit_edge import metrics as edge_metrics


class _RecordingCounter:
    """Stand-in for a real OTEL counter that records .add() calls."""

    def __init__(self):
        self.calls = []

    def add(self, amount, attributes=None):
        self.calls.append((amount, dict(attributes) if attributes else {}))


def test_with_counter_metric_sync_no_attributes():
    counter = _RecordingCounter()

    @edge_metrics.with_counter_metric(counter)
    def add(a, b):
        return a + b

    assert add(1, 2) == 3
    assert counter.calls == [(1, {})]


def test_with_counter_metric_async_no_attributes():
    counter = _RecordingCounter()

    @edge_metrics.with_counter_metric(counter)
    async def add(a, b):
        return a + b

    result = asyncio.run(add(2, 3))
    assert result == 5
    assert counter.calls == [(1, {})]


def test_with_counter_metric_sync_static_attributes():
    counter = _RecordingCounter()

    @edge_metrics.with_counter_metric(counter, attributes={"endpoint": "/x"})
    def f():
        return "ok"

    f()
    assert counter.calls == [(1, {"endpoint": "/x"})]


def test_with_counter_metric_callable_attributes_receives_args():
    counter = _RecordingCounter()

    @edge_metrics.with_counter_metric(
        counter,
        attributes=lambda a, b=None: {"a": str(a), "b": str(b)},
    )
    def f(a, b=None):
        return a

    f(1, b=2)
    assert counter.calls == [(1, {"a": "1", "b": "2"})]


def test_with_counter_metric_counts_even_when_wrapped_raises():
    counter = _RecordingCounter()

    @edge_metrics.with_counter_metric(counter)
    def f():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        f()
    assert counter.calls == [(1, {})]


def test_with_counter_metric_async_alias_emits_deprecation_warning():
    counter = _RecordingCounter()

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")

        @edge_metrics.with_counter_metric_async(counter)
        async def f():
            return 1

        asyncio.run(f())

    assert any(issubclass(w.category, DeprecationWarning) for w in captured)
    assert counter.calls == [(1, {})]


def test_wrapped_function_preserves_name_and_docstring():
    counter = _RecordingCounter()

    @edge_metrics.with_counter_metric(counter)
    def original(x):
        """original docstring."""
        return x

    assert original.__name__ == "original"
    assert "original docstring" in (original.__doc__ or "")


def test_publish_pose_counter_receives_robot_id_attribute(
    mock_mqtt_client, monkeypatch
):
    """RobotSession.publish_pose adds a robot_id attribute to its counter."""
    from inorbit_edge.robot import RobotSession

    calls = []

    def _spy_add(amount, attributes=None):
        calls.append((amount, dict(attributes) if attributes else {}))

    monkeypatch.setattr(edge_metrics.publish_pose_counter, "add", _spy_add)

    session = RobotSession(
        robot_id="test-robot-1", robot_name="test-robot-1", api_key="ak"
    )
    session.publish_pose(x=1.0, y=2.0, yaw=0.0, frame_id="map")

    assert calls, "counter was not called"
    amount, attrs = calls[0]
    assert amount == 1
    assert attrs.get("robot_id") == "test-robot-1"


def test_publish_laser_increments_laser_counter_once(mock_mqtt_client, monkeypatch):
    """publish_laser delegates to publish_lasers; count once, not on both methods."""
    from inorbit_edge.robot import RobotSession

    calls = []

    def _spy_add(amount, attributes=None):
        calls.append((amount, dict(attributes) if attributes else {}))

    monkeypatch.setattr(edge_metrics.publish_laser_counter, "add", _spy_add)

    session = RobotSession(robot_id="laser-bot", robot_name="laser-bot", api_key="ak")
    session.publish_laser(0, 0, 0, [1.0, 2.0], frame_id="map")

    assert len(calls) == 1
    assert calls[0][0] == 1
    assert calls[0][1].get("robot_id") == "laser-bot"


@pytest.mark.parametrize(
    "counter_name,method_name,method_kwargs",
    [
        (
            "publish_key_values_counter",
            "publish_key_values",
            {"key_values": {"k": "v"}},
        ),
        (
            "publish_odometry_counter",
            "publish_odometry",
            {"linear_distance": 1.0, "angular_distance": 0.1},
        ),
        ("publish_path_counter", "publish_path", {"path_points": []}),
    ],
)
def test_publish_methods_all_add_robot_id(
    mock_mqtt_client, monkeypatch, counter_name, method_name, method_kwargs
):
    """Each decorated publish_* method passes robot_id on its counter."""
    from inorbit_edge.robot import RobotSession

    calls = []
    monkeypatch.setattr(
        getattr(edge_metrics, counter_name),
        "add",
        lambda amount, attributes=None: calls.append(
            (amount, dict(attributes) if attributes else {})
        ),
    )

    session = RobotSession(
        robot_id="fleet-bot-7", robot_name="fleet-bot-7", api_key="ak"
    )
    try:
        getattr(session, method_name)(**method_kwargs)
    except Exception:
        # We only care that the counter was called before the body runs
        pass

    assert calls, f"counter {counter_name} was not called"
    amount, attrs = calls[0]
    assert amount == 1
    assert attrs.get("robot_id") == "fleet-bot-7"
