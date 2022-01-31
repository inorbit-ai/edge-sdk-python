# InOrbit Python Edge SDK

[![Build Status](https://github.com/inorbit-ai/edge-sdk-python/workflows/Build%20Main/badge.svg)](https://github.com/inorbit-ai/edge-sdk-python/actions)
[![Documentation](https://github.com/inorbit-ai/edge-sdk-python/workflows/Documentation/badge.svg)](https://inorbit.github.io/edge-sdk-python/)
[![Code Coverage](https://codecov.io/gh/inorbit/edge-sdk-python/branch/main/graph/badge.svg)](https://codecov.io/gh/inorbit/edge-sdk-python)

InOrbit Python Edge SDK

---

## Features

- Robot session handling through a `RobotSessionPool`.
- Publish key-values.
- Publish robot poses.
- Publish robot odometry.

## Quick Start

```python
from inorbit_edge.robot import RobotSessionFactory, RobotSessionPool

robot_session_factory = RobotSessionFactory(api_key="<YOUR_API_KEY>")

robot_session_pool = RobotSessionPool(robot_session_factory)

robot_session = robot_session_pool.get_session(
    robot_id="my_robot_id_123", robot_name="Python SDK Quick Start Robot"
)

robot_session.publish_pose(x=0.0, y=0.0, yaw=0.0)
```

## Installation

**Stable Release:** `pip install edge-sdk-python`<br>
**Development Head:** `pip install git+https://github.com/inorbit-ai/edge-sdk-python.git`

## Documentation

For full package documentation please visit [inorbit.github.io/edge-sdk-python](https://inorbit.github.io/edge-sdk-python).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for information related to developing the code.

## The Four Commands You Need To Know

1. `pip install -e .[dev]`

    This will install your package in editable mode with all the required development
    dependencies (i.e. `tox`).

2. `make build`

    This will run `tox` which will run all your tests in both Python 3.7
    and Python 3.8 as well as linting your code.

3. `make clean`

    This will clean up various Python and build generated files so that you can ensure
    that you are working in a clean environment.

4. `make docs`

    This will generate and launch a web browser to view the most up-to-date
    documentation for your Python package.
