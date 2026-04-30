# Build from repository root, e.g.:
#   docker build -f inorbit_edge/tests/demo/Dockerfile -t inorbit-edge-sdk-demo .
#
# Run: mount this folder from the host (example, map, user_scripts). Example from repo root:
#   docker run --rm -p 9464:9464 \
#     -v "$PWD/inorbit_edge/tests/demo:/demo:ro" \
#     -e INORBIT_URL=... \
#     -e INORBIT_API_URL=... \
#     -e INORBIT_API_KEY=... \
#     -e INORBIT_ACCOUNT_ID=... \
#     -e INORBIT_USE_SSL=true \
#     -e INORBIT_ROBOT_ID_PREFIX=$(hostname) \
#     inorbit-edge-sdk-demo

FROM python:3.12-slim-bookworm

WORKDIR /build

COPY README.md \
    requirements.txt requirements-dev.txt \
    requirements-video.txt requirements-telemetry.txt \
    setup.py ./

COPY inorbit_edge/ ./inorbit_edge/

RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir ".[video,telemetry]"

# Demo assets (example.py, map.png, user_scripts/) are expected from a host mount at /demo
WORKDIR /demo

# Default: export SDK metrics for Prometheus on 9464 (scrape /metrics on this port)
ENV INORBIT_METRICS_PORT=9464
ENV INORBIT_METRICS_ADDR=0.0.0.0

CMD ["python", "example.py"]
