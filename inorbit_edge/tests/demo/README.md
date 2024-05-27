# InOrbit Edge SDK demo

Code for generating synthetic data for simulating a fleet of robots. It uses the InOrbit Edge SDK for publishing robot
data to InOrbit. It also uses the InOrbit API for publishing map data (see `map.png` file).

## How to use

Export required environment variables and execute the `example.py` script. Use the `virtualenv` used on
the `CONTRIBUTING.md` guide.

```bash
export INORBIT_URL="https://control.inorbit.ai"
export INORBIT_API_URL="https://api.inorbit.ai"
export INORBIT_API_KEY="foobar123"
# Set when using InOrbit connect (make sure to update the robot keys
# in the example config first through
# https://api.inorbit.ai/docs/index.html#operation/generateRobotKey)
export INORBIT_ROBOT_CONFIG_FILE=`pwd`/robots_config_example.yaml
# Disable SSL for local development only
export INORBIT_USE_SSL="true"
# Optionally enable video streaming as camera "0"
export INORBIT_VIDEO_URL=/dev/video0

python example.py
```
