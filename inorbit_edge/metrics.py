# OpenTelemetry Metrics declarations and helper functions
#
# This file declares basic metrics for some SDK function calls. Other metrics
# can be added by connectors to monitor their own operations, following these
# examples.
#
# To export these metrics over a Prometheus HTTP endpoint, call
# :func:`setup_prometheus_meter_provider` once during initialization, then
# start the HTTP server with ``prometheus_client.start_http_server``. For
# example:
#
#   from inorbit_edge.metrics import setup_prometheus_meter_provider
#   from prometheus_client import start_http_server
#
#   setup_prometheus_meter_provider(
#       service_name="my-connector",
#       service_instance_id="robot-123",
#       service_version="1.2.3",
#   )
#   start_http_server(port=9090, addr="0.0.0.0")
#
# The helper below wires the pieces as follows:
#
# * OpenTelemetry API (``opentelemetry.metrics``): the stable API used by SDK
#   code to create meters and instruments such as counters.
# * OpenTelemetry SDK (``MeterProvider``): the runtime implementation that
#   stores metric data and feeds it to configured metric readers/exporters.
# * ``Resource``: metadata attached to all exported metrics, for example
#   service name, service instance, and version.
# * ``PrometheusMetricReader``: an OTEL reader that makes collected metric data
#   available to the Prometheus client registry when Prometheus scrapes.
# * ``prometheus_client.start_http_server``: not called here; the connector or
#   demo starts that HTTP server to expose the registry at ``/metrics``.
#
# When the optional ``telemetry`` extra is not installed, all instruments
# become no-ops and ``setup_prometheus_meter_provider`` returns False.
#
import functools
import inspect
import logging
import re

from deprecated import deprecated

logger = logging.getLogger(__name__)


class _NoOpInstrument:
    def add(self, *_args, **_kwargs):
        pass

    def record(self, *_args, **_kwargs):
        pass

    def set(self, *_args, **_kwargs):
        pass


class _NoOpMeter:
    def create_counter(self, *_args, **_kwargs):
        return _NoOpInstrument()

    def create_up_down_counter(self, *_args, **_kwargs):
        return _NoOpInstrument()

    def create_histogram(self, *_args, **_kwargs):
        return _NoOpInstrument()

    def create_gauge(self, *_args, **_kwargs):
        return _NoOpInstrument()

    def create_observable_gauge(self, *_args, **_kwargs):
        return _NoOpInstrument()

    def create_observable_counter(self, *_args, **_kwargs):
        return _NoOpInstrument()

    def create_observable_up_down_counter(self, *_args, **_kwargs):
        return _NoOpInstrument()


try:
    # OTEL API package: lightweight surface used by the SDK to create meters.
    # Importing this alone is enough for no-export metrics, but not enough to
    # expose data to Prometheus; that needs the SDK provider and reader below.
    from opentelemetry import metrics as _otel_metrics
    # Re-exported for connectors that define observable instruments.
    from opentelemetry.metrics import Observation  # noqa: F401

    OTEL_API_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised when telemetry extra is missing
    OTEL_API_AVAILABLE = False
    Observation = None  # type: ignore[assignment]  # noqa: F401


try:
    # PrometheusMetricReader bridges OTEL SDK metrics into prometheus-client's
    # registry. MeterProvider is the SDK runtime that owns readers. Resource
    # carries service metadata exported as Prometheus target_info labels.
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.sdk.metrics import MeterProvider as _SdkMeterProvider
    from opentelemetry.sdk.resources import Resource

    PROMETHEUS_EXPORTER_AVAILABLE = True
except ImportError:  # pragma: no cover
    PROMETHEUS_EXPORTER_AVAILABLE = False


def get_meter(name):
    """Return an OpenTelemetry Meter for ``name``.

    A Meter is the factory for instruments (counters, gauges, histograms). SDK
    code records through instruments; exporter setup is intentionally separate
    so importing the package does not force telemetry dependencies.

    When the ``telemetry`` extra is not installed, returns a no-op meter
    whose instruments accept any call without raising.
    """
    if OTEL_API_AVAILABLE:
        return _otel_metrics.get_meter(name)
    return _NoOpMeter()


def _sanitize_prometheus_prefix(prefix):
    """Return a Prometheus-safe metric name prefix."""
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", prefix)
    if sanitized and sanitized[0].isdigit():
        return f"_{sanitized}"
    return sanitized


def setup_prometheus_meter_provider(
    service_name,
    service_instance_id,
    service_version=None,
    extra_resource_attributes=None,
    exporter_namespace=None,
):
    """Install a global OTEL MeterProvider with a Prometheus reader.

    This prepares OTEL metric collection but does not open a network port.
    Call ``prometheus_client.start_http_server`` after this to serve the
    Prometheus scrape endpoint.

    Component roles:
      * ``Resource``: service-level labels attached to all metrics.
      * ``PrometheusMetricReader``: reads OTEL SDK metric data on scrape and
        registers it with prometheus-client.
      * ``MeterProvider``: the global OTEL SDK runtime used by meters returned
        from ``get_meter``.

    OpenTelemetry permits only one provider per process; subsequent calls may
    be ignored with a warning by the OTEL runtime.

    Returns True when this provider became active. Returns False when the
    OpenTelemetry / Prometheus exporter dependencies are not installed (in
    which case all instrument calls become no-ops), or when OpenTelemetry kept
    an existing provider instead.

    Args:
        service_name: OTLP ``service.name`` resource attribute. Also used as
            the default Prometheus metric name prefix.
        service_instance_id: OTLP ``service.instance.id`` resource attribute.
            Should be unique per process on a host.
        service_version: optional OTLP ``service.version``.
        extra_resource_attributes: optional dict of extra Resource attributes.
        exporter_namespace: optional Prometheus metric name prefix. Defaults
            to ``service_name``.

    The final Prometheus prefix is sanitized by replacing Prometheus-unsafe
    characters with ``_``.
    """
    if not (OTEL_API_AVAILABLE and PROMETHEUS_EXPORTER_AVAILABLE):
        logger.info(
            "Prometheus metrics provider not configured because telemetry "
            "dependencies are missing. Install the 'telemetry' extra to "
            "enable metrics export."
        )
        return False

    attrs = {
        "service.name": service_name,
        "service.instance.id": service_instance_id,
    }
    if service_version:
        attrs["service.version"] = service_version
    if extra_resource_attributes:
        attrs.update(extra_resource_attributes)

    # Resource attributes are exported as target_info labels. They identify
    # which process/service emitted otherwise identical metric names.
    resource = Resource.create(attrs)

    # The reader translates OTEL metric data into Prometheus metric families.
    # ``prefix`` namespaces metric names, e.g. calls_publish_pose_total becomes
    # my_connector_calls_publish_pose_total.
    prefix = _sanitize_prometheus_prefix(exporter_namespace or service_name)
    reader = PrometheusMetricReader(prefix=prefix)

    # The provider owns the reader and becomes the implementation behind the
    # global OTEL API. Meters created via get_meter() record through it.
    provider = _SdkMeterProvider(metric_readers=[reader], resource=resource)
    _otel_metrics.set_meter_provider(provider)
    return _otel_metrics.get_meter_provider() is provider


# Module-level instruments. If telemetry is installed before this module is
# imported, these are real OTEL counters. Otherwise they are no-op counters so
# callers can use the SDK without installing or configuring OpenTelemetry.
meter = get_meter("inorbit_edge_sdk")

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


def attrs_from_self(*names):
    """Build an attributes extractor for :func:`with_counter_metric` on methods.

    The returned callable reads each named attribute from the bound instance
    (the first positional arg) and returns them as an OTEL attributes dict.

    Use this on instance methods to add per-call attributes that come from
    the instance's own state, for example::

        @with_counter_metric(
            publish_pose_counter, attributes=attrs_from_self("robot_id")
        )
        def publish_pose(self, ...):
            ...

    Multiple attributes are supported::

        attrs_from_self("robot_id", "session_id")

    Raises ``AttributeError`` at call time if any name is not an attribute of
    the instance.
    """

    def _extract(self, *_args, **_kwargs):
        return {name: getattr(self, name) for name in names}

    return _extract


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


@deprecated(
    version="2.0.2",
    reason=(
        "use with_counter_metric(), which now auto-detects async functions"
    ),
)
def with_counter_metric_async(metric):
    """Deprecated alias for :func:`with_counter_metric`.

    Prefer ``@with_counter_metric(...)``, which now detects async functions
    automatically.
    """

    return with_counter_metric(metric)
