# InOrbit Python Edge SDK

[![Build Status](https://github.com/inorbit-ai/edge-sdk-python/workflows/Build%20Main/badge.svg)](https://github.com/inorbit-ai/edge-sdk-python/actions)
[![Code Coverage](https://codecov.io/gh/inorbit/edge-sdk-python/branch/main/graph/badge.svg)](https://codecov.io/gh/inorbit/edge-sdk-python)

The `InOrbit Edge SDK` allows Python programs to communicate with `InOrbit` platform on behalf of robots - providing robot data and handling robot actions. It's goal is to ease the integration between `InOrbit` and any other software that handles robot data.

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
            - `result_function` can be called to report command execution result. It
            has the following signature: `result_function(return_code)`.
            - `progress_function` can be used to report command output and has the
            following signature: `progress_function(output, error)`.
            - `metadata` is reserved for the future and will contains additional
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
robot_session_factory.register_executable_commands("./user_scripts", r".*\.sh")

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

For full package documentation please visit [InOrbit Developer Portal](https://developer.inorbit.ai/docs?hsLang=en#edge-sdk).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for information related to developing the code.

## The Three Commands You Need To Know

1. `pip install -e .[dev]`

    This will install your package in editable mode with all the required development
    dependencies (i.e. `tox`).

2. `make build`

    This will run `tox` which will run all your tests in both Python 3.7
    and Python 3.8 as well as linting your code.

3. `make clean`

    This will clean up various Python and build generated files so that you can ensure
    that you are working in a clean environment.
