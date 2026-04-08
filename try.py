import math
import time

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
    api_key="Cy6_oBXAeLn8JiZe",
    endpoint="http://localdev.com:3000//cloud_sdk_robot_config",
    use_ssl=False,
)

# Register commands handlers. Note that all handlers are invoked.
robot_session_factory.register_command_callback(my_command_handler)
robot_session_factory.register_commands_path("./user_scripts", r".*\.sh")

robot_session_pool = RobotSessionPool(robot_session_factory)

robot_session = robot_session_pool.get_session(
    robot_id="my_robot_id_123", robot_name="Python SDK Quick Start Robot"
)

# Publish map once at startup
robot_session.publish_map(
    file="inorbit_edge/tests/demo/map.png",
    map_id="test_map",
    map_label="Test Map",
    x=-10.0,
    y=-10.0,
    resolution=0.05,
)
print("Map published")

step = 0
while True:
    # Circular pose
    angle = (step % 360) * math.pi / 180
    x = 3.0 * math.cos(angle)
    y = 3.0 * math.sin(angle)
    yaw = angle + math.pi / 2

    robot_session.publish_pose(x=x, y=y, yaw=yaw)

    robot_session.publish_key_values({
        "status": "running",
        "step": step,
        "battery": max(0, 100 - (step % 100)),
    })

    print(f"Step {step}: pose=({x:.2f}, {y:.2f}, {yaw:.2f})")
    step += 1
    time.sleep(1)
