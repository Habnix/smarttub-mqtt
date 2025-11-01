# Docker Build Instructions

Since Docker is not available in the current environment, you can build the image on a system with Docker/Podman installed:

## Build Command

```bash
docker build -t smarttub-mqtt:latest .
```

Or with Podman:

```bash
podman build -t smarttub-mqtt:latest .
```

## Expected Build Output

The multi-stage build will:

1. **Stage 1 (Builder)**:
   - Use Python 3.11-slim base
   - Install build dependencies (gcc, make, libssl-dev)
   - Create virtual environment in `/opt/venv`
   - Install Python dependencies from pyproject.toml
   
2. **Stage 2 (Runtime)**:
   - Use minimal Python 3.11-slim base
   - Copy only virtual environment from builder (no build tools)
   - Create non-root user `smarttub` (UID 1000)
   - Copy application source code
   - Create `/config` and `/log` directories
   - Set up health check endpoint
   - Configure entrypoint

## Image Size Estimate

- **Builder stage**: ~500-700 MB (temporary)
- **Final runtime image**: ~200-300 MB
  - Base Python 3.11-slim: ~120 MB
  - Virtual environment: ~80-150 MB
  - Application code: ~5-10 MB

## Test Build

After building, inspect the image:

```bash
# Check image size
docker images smarttub-mqtt:latest

# Inspect layers
docker history smarttub-mqtt:latest

# Test container creation (without running)
docker create --name smarttub-test smarttub-mqtt:latest
docker inspect smarttub-test
docker rm smarttub-test
```

## Run Container

```bash
docker run -d \
  --name smarttub-mqtt \
  -p 8080:8080 \
  -v $(pwd)/config:/config \
  -v $(pwd)/log:/log \
  -e SMARTTUB_EMAIL=your@email.com \
  -e SMARTTUB_PASSWORD=yourpassword \
  -e MQTT_BROKER=mqtt://broker:1883 \
  smarttub-mqtt:latest
```

## Health Check

The container includes a health check that verifies the Web UI is responding:

```bash
# Check container health status
docker ps --filter name=smarttub-mqtt

# View health check logs
docker inspect smarttub-mqtt | jq '.[0].State.Health'
```

## Validation Checklist

- [ ] Image builds successfully without errors
- [ ] Final image size < 350 MB
- [ ] Non-root user (UID 1000) configured
- [ ] Health check passes after startup
- [ ] Volumes mounted correctly (/config, /log)
- [ ] Environment variables validated on startup
- [ ] Graceful shutdown on SIGTERM
- [ ] Web UI accessible on port 8080
- [ ] MQTT connection successful
- [ ] Logs written to /log directory
