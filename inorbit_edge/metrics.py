# OpenTelemetry Metrics declarations and helper functions
#
# This file declares basic metrics for some SDK function calls. Other metrics
# can be added by connectors to monitor their own operations, following these
# examples.
#
# In all cases, initialization code is necessary to export these metrics.
# For example, to export metrics from a connector through a Prometheus HTTP
# endpoint, add the following to your initialization code:
#
#   from opentelemetry import metrics
#   from opentelemetry.exporter.prometheus import PrometheusMetricReader
#   from opentelemetry.sdk.metrics import MeterProvider
#   from opentelemetry.sdk.resources import Resource
#   from prometheus_client import start_http_server
#
#   resource = Resource(attributes={"service.name": "my-connector"})
#   # Note: Do not use "-" in the MetricsReader namefor GCP envs
#   metric_reader = PrometheusMetricReader("my_connector")
#   meter_provider = MeterProvider(metric_readers=[metric_reader], resource=resource)
#   metrics.set_meter_provider(meter_provider)
#   start_http_server(port=prometheus_port, addr=prometheus_host)
#
import functools
import inspect
import warnings

try:
    from opentelemetry import metrics as _otel_metrics

    def _get_meter():
        return _otel_metrics.get_meter("inorbit_edge_sdk")

except ImportError:  # pragma: no cover
    # Optional "telemetry" extra not installed

    class _NoOpCounter:
        def add(self, amount, attributes=None):
            pass

    class _NoOpMeter:
        def create_counter(self, name, unit="", description=""):
            return _NoOpCounter()

    def _get_meter():
        return _NoOpMeter()


meter = _get_meter()

publish_map_counter = meter.create_counter(
    "calls_publish_map", "1", "number of calls to publish maps"
)
publish_camera_frame_counter = meter.create_counter(
    "calls_publish_camera_frame", "1", "number of calls to publish camera frames"
)
publish_pose_counter = meter.create_counter(
    "calls_publish_pose", "1", "number of calls to publish poses"
)
publish_key_values_counter = meter.create_counter(
    "calls_publish_key_values", "1", "number of calls to publish key-values"
)
publish_system_stats_counter = meter.create_counter(
    "calls_publish_system_stats", "1", "number of calls to publish system stats"
)
publish_odometry_counter = meter.create_counter(
    "calls_publish_odometry", "1", "number of calls to publish odometry"
)
publish_laser_counter = meter.create_counter(
    "calls_publish_lasers", "1", "number of calls to publish laser(s)"
)
publish_path_counter = meter.create_counter(
    "calls_publish_path", "1", "number of calls to publish paths"
)


def with_counter_metric(metric, attributes=None):
    """Decorator: increment ``metric`` by 1 on every call.

    Works on sync and async functions (auto-detected).

    attributes:
      * ``None`` — no per-call attributes (identical to the original behavior)
      * ``dict`` — static per-call attributes
      * ``callable`` — invoked with the wrapped function's ``*args, **kwargs``;
        must return a dict of attributes
    """

    def _resolve_attrs(args, kwargs):
        if attributes is None:
            return {}
        if callable(attributes):
            return attributes(*args, **kwargs) or {}
        return dict(attributes)

    def decorator(func):
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                metric.add(1, _resolve_attrs(args, kwargs))
                return await func(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            metric.add(1, _resolve_attrs(args, kwargs))
            return func(*args, **kwargs)

        return sync_wrapper

    return decorator


def with_counter_metric_async(metric):
    """Deprecated alias for :func:`with_counter_metric`.

    Prefer ``@with_counter_metric(...)``, which now detects async functions
    automatically.
    """

    warnings.warn(
        "with_counter_metric_async is deprecated; use with_counter_metric "
        "which now auto-detects async functions.",
        DeprecationWarning,
        stacklevel=2,
    )
    return with_counter_metric(metric)
