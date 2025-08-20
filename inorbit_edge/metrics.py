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

from opentelemetry import metrics

meter = metrics.get_meter("inorbit_edge_sdk")

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


def with_counter_metric(metric):
    """
    Decorator to count the number of calls to a function
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper_decorator(*args, **kwargs):
            metric.add(1)
            return func(*args, **kwargs)

        return wrapper_decorator

    return decorator


def with_counter_metric_async(metric):
    """
    Decorator to count the number of calls to a function
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper_decorator(*args, **kwargs):
            metric.add(1)
            return await func(*args, **kwargs)

        return wrapper_decorator

    return decorator
