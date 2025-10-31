# Docker usage for smarttub-mqtt

This document explains the minimal Docker build and run steps for the project.

Build image:

```bash
docker build -t smarttub-mqtt .
```

Run (mounted config directory):

```bash
mkdir -p /opt/smarttub-mqtt/config
# put your .env and smarttub.yaml into /opt/smarttub-mqtt/config
docker run -d \
  --name smarttub-mqtt \
  --restart unless-stopped \
  -v /opt/smarttub-mqtt/config:/config \
  -p 8080:8080 \
  smarttub-mqtt:latest
```

Dockerfile recommendation: use `python:3.11-slim`, install requirements, copy `src/` and `config` entrypoint to `python -m src.cli.run`.

For CI: build and push to registry, tag the image with the repo semantic version.
