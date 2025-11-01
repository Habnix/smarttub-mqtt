# Quickstart: SmartTub MQTT Bridge

## Prerequisites

- Python 3.11+
- Docker 24+
- Running MQTT broker reachable by both OpenHAB and this service
- SmartTub account credentials (email/password or token) supported by `python-smarttub`
- OpenHAB MQTT binding configured to connect to the shared broker

## Configuration

1. Copy `config/example.yaml` to `config/smarttub.yaml` (final path mounted into container).
2. Populate required sections:
   - `smarttub`: email, password (or token), polling interval (default 30s), retry count.
   - `mqtt`: broker URL, username/password (if any), base topic prefix (`smarttub-mqtt`), TLS settings.
   - `web`: host `0.0.0.0`, port `8080`, optional basic auth credentials.
   - `logging`: level (`info` default), enable MQTT forwarding boolean.
3. Create `.env` file with secrets (e.g., `SMARTTUB_EMAIL`, `SMARTTUB_PASSWORD`) if preferring environment-based secrets.

## Local Development Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export SMARTTUB_CONFIG=$(pwd)/config/smarttub.yaml
export MQTT_BROKER_URL=mqtt://localhost:1883
export LOG_LEVEL=debug
python -m src.cli.run
```

- Service starts polling SmartTub, publishes to MQTT, and hosts Web UI at `http://localhost:8080`.
- Visit `/ui` to view dashboard; use OpenHAB to subscribe to `smarttub-mqtt/state/#` to verify telemetry.

## Testing

- **Unit tests**: `pytest tests/unit`
- **Integration tests** (requires MQTT test broker + SmartTub mocks): `pytest tests/integration`
- **Contract tests** (HTTP + MQTT schemas): `pytest tests/contract`
- Ensure tests fail before implementation updates; update fixtures as needed.

## Web UI Usage

1. Navigate to `http://localhost:8080/ui`.
2. Overview panel shows current component states and last update timestamps.
3. Controls tab lists actions permitted by capability discovery; buttons publish commands via MQTT.
4. Log tab streams recent events (filtered by selected log level).

## Logging Configuration

- Adjust `logging.level` in config or set `LOG_LEVEL` env var (`debug`, `info`, `warning`, `error`).
- Enable MQTT log forwarding by setting `logging.mqtt_forwarding: true`; logs appear on `smarttub-mqtt/meta/logs` topic.
- Local log files (if enabled) stored under `/var/log/smarttub-mqtt` (configurable path).

## Docker Build & Run

```bash
docker build -t smarttub-mqtt:latest .
```

Run alongside OpenHAB (example):

```bash
docker run \
  --name smarttub-mqtt \
  --network=host \
  -e SMARTTUB_EMAIL=you@example.com \
  -e SMARTTUB_PASSWORD=•••• \
  -e MQTT_BROKER_URL=mqtt://localhost:1883 \
  -e LOG_LEVEL=info \
  -v $(pwd)/config:/config:ro \
  -p 8080:8080 \
  smarttub-mqtt:latest
```

- Container expects `/config/smarttub.yaml` and `.env` (optional).
- Healthcheck pings `http://localhost:8080/api/state` every 30s.

## Verification Checklist

- Web UI loads with live state data and updates on pool changes.
- OpenHAB items bound to `smarttub-mqtt/state/<component>/<metric>` update within 5 seconds.
- Issuing command via OpenHAB changes pool state and publishes confirmation on `command/<component>/response`.
- Logs visible locally and (if enabled) via MQTT topic.

## Troubleshooting

- **MQTT connection errors**: verify broker credentials and TLS options; check `smarttub-mqtt/meta/heartbeat` payloads.
- **SmartTub authentication failure**: re-run login in python-smarttub example to confirm credentials; rotate token if expired.
- **Command stuck in pending**: inspect logs for error details, ensure capability profile includes the target command.
- **Docker networking**: if not using `--network=host`, ensure ports 8080 (HTTP) and 1883 (MQTT) are reachable inside container.
