# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
# SPDX-License-Identifier: MIT

import asyncio
import warnings

import pytest

from opentelemetry.metrics import _internal as _otel_internal
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


# --- Tests for the public Prometheus-setup helpers ------------------------


@pytest.fixture(autouse=False)
def reset_meter_provider():
    """Reset OTEL global provider state before/after the test."""
    from opentelemetry.util._once import Once

    _otel_internal._METER_PROVIDER = None
    _otel_internal._PROXY_METER_PROVIDER = _otel_internal._ProxyMeterProvider()
    _otel_internal._METER_PROVIDER_SET_ONCE = Once()
    yield
    _otel_internal._METER_PROVIDER = None
    _otel_internal._PROXY_METER_PROVIDER = _otel_internal._ProxyMeterProvider()
    _otel_internal._METER_PROVIDER_SET_ONCE = Once()


def test_get_meter_returns_real_meter_when_otel_available():
    m = edge_metrics.get_meter("inorbit_test")
    # When OTEL is available we get a Meter (likely a _ProxyMeter); not the
    # local _NoOpMeter sentinel.
    assert m is not None
    counter = m.create_counter("inorbit.test.counter")
    counter.add(1)


def test_setup_prometheus_meter_provider_installs_resource(reset_meter_provider):
    from opentelemetry import metrics as otel_metrics
    from opentelemetry.sdk.metrics import MeterProvider

    installed = edge_metrics.setup_prometheus_meter_provider(
        service_name="inorbit_connector",
        service_instance_id="r-1",
        service_version="1.0.0",
        extra_resource_attributes={"site": "lab"},
    )
    assert installed is True

    provider = otel_metrics.get_meter_provider()
    assert isinstance(provider, MeterProvider)
    attrs = dict(provider._sdk_config.resource.attributes)
    assert attrs["service.name"] == "inorbit_connector"
    assert attrs["service.instance.id"] == "r-1"
    assert attrs["service.version"] == "1.0.0"
    assert attrs["site"] == "lab"


def test_setup_prometheus_meter_provider_returns_false_when_disabled(monkeypatch):
    monkeypatch.setattr(edge_metrics, "PROMETHEUS_EXPORTER_AVAILABLE", False)
    installed = edge_metrics.setup_prometheus_meter_provider(
        service_name="x", service_instance_id="y"
    )
    assert installed is False


def test_setup_prometheus_meter_provider_uses_service_name_as_prefix(monkeypatch):
    captured = {}

    class _Reader:
        def __init__(self, *, prefix=""):
            captured["prefix"] = prefix

    class _Provider:
        def __init__(self, metric_readers, resource):
            captured["provider"] = self
            self.metric_readers = metric_readers
            self.resource = resource

    class _Resource:
        @staticmethod
        def create(attrs):
            return attrs

    monkeypatch.setattr(edge_metrics, "OTEL_API_AVAILABLE", True)
    monkeypatch.setattr(edge_metrics, "PROMETHEUS_EXPORTER_AVAILABLE", True)
    monkeypatch.setattr(edge_metrics, "PrometheusMetricReader", _Reader)
    monkeypatch.setattr(edge_metrics, "_SdkMeterProvider", _Provider)
    monkeypatch.setattr(edge_metrics, "Resource", _Resource)
    monkeypatch.setattr(
        edge_metrics._otel_metrics,
        "set_meter_provider",
        lambda provider: captured.__setitem__("active_provider", provider),
    )
    monkeypatch.setattr(
        edge_metrics._otel_metrics,
        "get_meter_provider",
        lambda: captured["active_provider"],
    )

    installed = edge_metrics.setup_prometheus_meter_provider(
        service_name="inorbit-connector",
        service_instance_id="r-1",
    )

    assert installed is True
    assert captured["prefix"] == "inorbit-connector"


def test_setup_prometheus_meter_provider_accepts_prefix_override(monkeypatch):
    captured = {}

    class _Reader:
        def __init__(self, *, prefix=""):
            captured["prefix"] = prefix

    class _Provider:
        def __init__(self, metric_readers, resource):
            captured["provider"] = self
            self.metric_readers = metric_readers
            self.resource = resource

    class _Resource:
        @staticmethod
        def create(attrs):
            return attrs

    monkeypatch.setattr(edge_metrics, "OTEL_API_AVAILABLE", True)
    monkeypatch.setattr(edge_metrics, "PROMETHEUS_EXPORTER_AVAILABLE", True)
    monkeypatch.setattr(edge_metrics, "PrometheusMetricReader", _Reader)
    monkeypatch.setattr(edge_metrics, "_SdkMeterProvider", _Provider)
    monkeypatch.setattr(edge_metrics, "Resource", _Resource)
    monkeypatch.setattr(
        edge_metrics._otel_metrics,
        "set_meter_provider",
        lambda provider: captured.__setitem__("active_provider", provider),
    )
    monkeypatch.setattr(
        edge_metrics._otel_metrics,
        "get_meter_provider",
        lambda: captured["active_provider"],
    )

    installed = edge_metrics.setup_prometheus_meter_provider(
        service_name="inorbit-connector",
        service_instance_id="r-1",
        exporter_namespace="inorbit_connector",
    )

    assert installed is True
    assert captured["prefix"] == "inorbit_connector"


def test_otel_api_available_reflects_import_status():
    # In the test environment the telemetry extra is installed, so OTEL is
    # available. The flag is the source of truth for callers.
    assert edge_metrics.OTEL_API_AVAILABLE is True
    assert edge_metrics.Observation is not None


# --- Tests for attrs_from_self ------------------------------------------


def test_attrs_from_self_extracts_named_attributes():
    extract = edge_metrics.attrs_from_self("robot_id", "site")

    class _Stub:
        robot_id = "r-7"
        site = "lab"

    assert extract(_Stub()) == {"robot_id": "r-7", "site": "lab"}


def test_attrs_from_self_used_with_with_counter_metric():
    counter = _RecordingCounter()

    class _Thing:
        robot_id = "r-1"

        @edge_metrics.with_counter_metric(
            counter, attributes=edge_metrics.attrs_from_self("robot_id")
        )
        def do_work(self, _arg):
            return _arg

    _Thing().do_work(42)
    assert counter.calls == [(1, {"robot_id": "r-1"})]


def test_attrs_from_self_raises_when_attribute_missing():
    extract = edge_metrics.attrs_from_self("missing_attr")

    class _Stub:
        pass

    with pytest.raises(AttributeError):
        extract(_Stub())
