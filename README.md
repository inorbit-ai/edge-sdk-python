# InOrbit Python Edge SDK

![Build](https://github.com/inorbit-ai/edge-sdk-python/actions/workflows/build-main.yml/badge.svg) ![License](https://img.shields.io/badge/License-MIT-yellow.svg) ![PyPI - Package Version](https://img.shields.io/pypi/v/inorbit-edge) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/inorbit-edge)

The `InOrbit Edge SDK` allows Python programs to communicate with `InOrbit`
platform on behalf of robots - providing robot data and handling robot actions.
Its goal is to ease the integration between `InOrbit` and any other software
that handles robot data.

---

## Features

- Robot session handling through a `RobotSessionPool`.
- Publish key-values.
- Publish robot poses.
- Publish robot odometry.
- Publish robot path.
- Publish robot laser.
- Execute callbacks on Custom Action execution.
- Execute scripts (or any program) in response to Custom Action execution.

## Quick Start

```python
from inorbit_edge.robot import RobotSessionFactory, RobotSessionPool


def my_command_handler(robot_id, command_name, args, options):
    """Callback for processing custom command calls.

    Args:
        robot_id (str): InOrbit robot ID
        command_name (str): InOrbit command e.g. 'customCommand'
        args (list): Command arguments
        options (dict): object that includes
            - `result_function` can be called to report command execution
            result with the following signature: `result_function(return_code)`
            - `progress_function` can be used to report command output with
            the following signature: `progress_function(output, error)`
            - `metadata` is reserved for the future and will contain additional
            information about the received command request.
    """
    if command_name == "customCommand":
        print(f"Received '{command_name}' for robot '{robot_id}'!. {args}")
        # Return '0' for success
        options["result_function"]("0")


robot_session_factory = RobotSessionFactory(
    api_key="<YOUR_API_KEY>"
)

# Register commands handlers. Note that all handlers are invoked.
robot_session_factory.register_command_callback(my_command_handler)
robot_session_factory.register_commands_path("./user_scripts", r".*\.sh")

robot_session_pool = RobotSessionPool(robot_session_factory)

robot_session = robot_session_pool.get_session(
    robot_id="my_robot_id_123", robot_name="Python SDK Quick Start Robot"
)

robot_session.publish_pose(x=0.0, y=0.0, yaw=0.0)
```

## Installation

**Stable Release:** `pip install inorbit-edge`<br>

**Development Head:** `pip install git+https://github.com/inorbit-ai/edge-sdk-python.git`

## Documentation

For full package documentation please
visit [InOrbit Developer Portal](https://developer.inorbit.ai/docs?hsLang=en#edge-sdk).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for information related to developing
the code.

## The Three Commands You Need To Know

1. `pip install -e .[dev]`

   This will install your package in editable mode with all the required
   development dependencies (i.e. `tox`).

2. `make build`

   This will run `tox` which will run all your tests in Python 3.10 - 3.13 as
   well as linting your code.

3. `make clean`

   This will clean up various Python and build generated files so that you can
   ensure that you are working in a clean environment.

## Metrics

The SDK is capable of collecting internal metrics such as number of calls to
publishing functions. It uses [OpenTelemetry](https://opentelemetry.io/),
which supports various exporting mechanisms.
Connectors are responsible for configuring the exporter of their choice;
as well as adding more metrics if they chose to do so.

To do so, add these `opentelemetry-api` and `opentelemetry-sdk` packages
to the connector project. Depending on the exporter, another package such
as `opentelemetry-exporter-prometheus` (for Prometheus) is required.
The following is an example initialization code that enables a
[Prometheus](https://prometheus.io/) HTTP endpoint, where all SDK metrics
(including system metrics such as CPU usage) and any metric added by the
connector can be scraped and exported to any external system (Grafana,
StackDriver, etc.)

```
from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from prometheus_client import start_http_server

# ...

resource = Resource(attributes={"service.name": "my-connector"})
# Note: Do not use "-" in the MetricsReader namefor GCP envs
metric_reader = PrometheusMetricReader("my_connector")
meter_provider = MeterProvider(metric_readers=[metric_reader], resource=resource)
metrics.set_meter_provider(meter_provider)
start_http_server(port=9464, addr="0.0.0.0")
```
