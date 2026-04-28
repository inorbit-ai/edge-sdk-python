# InOrbit Edge SDK demo

Code for generating synthetic data for simulating a fleet of robots. It uses the InOrbit Edge SDK for publishing robot
data to InOrbit. It also uses the InOrbit API for publishing map data (see `map.png` file).

## How to use

From a virtual environment (see `CONTRIBUTING.md`), install the SDK with the video and telemetry extras from the
repository root, `cd` into this directory so paths such as `./user_scripts` resolve correctly, then set environment
variables and run `example.py`.

```bash
cd /path/to/edge-sdk-python
pip install -e '.[video,telemetry]'
cd inorbit_edge/tests/demo

export INORBIT_URL="https://control.inorbit.ai"
export INORBIT_API_URL="https://api.inorbit.ai"
export INORBIT_API_KEY="foobar123"
# TLS to the MQTT broker defaults to on. For a local broker without TLS: INORBIT_USE_SSL=false
# Optionally enable video streaming as camera "0"
export INORBIT_VIDEO_URL=/dev/video0

# Optional: Prometheus scrape endpoint for SDK internal metrics (requires [telemetry])
export INORBIT_METRICS_PORT=9464
export INORBIT_METRICS_ADDR=0.0.0.0

python example.py
```

Robot ids are always `<prefix>_edgesdk_demo_0`, `<prefix>_edgesdk_demo_1`, … The prefix is `INORBIT_ROBOT_ID_PREFIX` and is mandatory.

With `INORBIT_METRICS_PORT` set, the demo configures OpenTelemetry before importing the SDK, then serves metrics at
`http://$INORBIT_METRICS_ADDR:$INORBIT_METRICS_PORT/metrics` (e.g. curl from the host if the port is published).

## Run in a throwaway Docker container

The image only installs the SDK and dependencies. **Mount the demo directory** from your checkout so `example.py`,
`map.png`, and `user_scripts/` come from the host (edit the demo without rebuilding the image).

Build from the **repository root**:

```bash
docker build -f inorbit_edge/tests/demo/Dockerfile -t inorbit-edge-sdk-demo .
```

Run from the **repository root** (adjust paths if you run from elsewhere). Publish `9464` if you want Prometheus
metrics on the host:

```bash
docker run --rm -p 9464:9464 \
  -v "$PWD/inorbit_edge/tests/demo:/demo:ro" \
  -e INORBIT_URL=... -e INORBIT_API_URL=... -e INORBIT_API_KEY=... \
  -e INORBIT_ACCOUNT_ID=... \
  -e INORBIT_ROBOT_ID_PREFIX=$(hostname) \
  inorbit-edge-sdk-demo
```

`INORBIT_USE_SSL` defaults to **true** in the demo (required for InOrbit staging/production). Only set
`INORBIT_USE_SSL=false` if you use a local broker without TLS.

The image sets `INORBIT_METRICS_PORT=9464` and `INORBIT_METRICS_ADDR=0.0.0.0` by default; override or unset
`INORBIT_METRICS_PORT` to disable the metrics HTTP server.
