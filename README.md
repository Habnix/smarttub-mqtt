# smarttub-mqtt

Connect a SmartTub hot tub to an external MQTT broker, with a Web UI for
monitoring, controls and light-mode discovery.

![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.13%2B-blue)

## Features

- Temperature, heater, pump, light and filtration status and controls.
- MQTT topics per device, command results and data freshness indicators.
- Web dashboard, error diagnostics and optional Basic Authentication.
- Light-mode discovery with saved results and recovery after interruptions.

## Quick start

Requires Docker Compose, a SmartTub account and a reachable MQTT broker.
The included Compose file uses `willnix/smarttub-mqtt:0.4.0`; that release must
be published first. Check the [available image tags](https://hub.docker.com/r/willnix/smarttub-mqtt/tags).

```bash
git clone https://github.com/Habnix/smarttub-mqtt.git
cd smarttub-mqtt
cp config/.env.example config/.env
mkdir -p logs
```

Edit `config/.env`: set `SMARTTUB_EMAIL`, `SMARTTUB_PASSWORD` and
`MQTT_BROKER_URL`, plus broker credentials if required. Keep
`DISCOVERY_MODE=off` for normal use. Then protect the file:

```bash
chmod 600 config/.env
```

On Linux, the container's UID `1000` needs access to the service directories:

```bash
sudo chown -R 1000:1000 config logs
```

Docker Desktop usually does not need this ownership change. On Linux, use
`sudoedit config/.env` for later edits if your user has a different UID.

```bash
docker compose up -d
docker compose logs -f smarttub-mqtt
```

Open [localhost:8080](http://localhost:8080), or port 8080 on your Docker host.
Keep `config/` and `logs/` when upgrading; they hold persistent runtime data.
Never commit credentials or runtime files.

## Multiple hot tubs

The current bridge monitors and controls **one hot tub per running instance**.
Set `SMARTTUB_DEVICE_ID` to select it; otherwise, the first device returned by
the account is selected. Detecting several devices does not enable simultaneous
monitoring and control of all of them.

This is an application limitation. Several bridge containers can run on the
same Docker host; use a distinct device ID, MQTT prefix, data directories and
host port for each. Multiple hot tubs within one container are not currently
supported.

## Security and discovery

Use the Web UI on a trusted network. Otherwise, enable `WEB_AUTH_ENABLED=true`
with your own credentials and use a VPN or HTTPS proxy for remote access.
Never expose port 8080 directly to the internet. Light-mode discovery changes
the actual lights; start it deliberately.

## Development

Requires Python 3.13 or newer:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
./scripts/quality-check.sh
```

To test workspace changes in Docker:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

## Documentation

- [Container installation, configuration and upgrades](docs/dockerhub.md)
- [Complete environment settings](config/.env.example) and [configuration reference](docs/configuration-reference.md)
- [Runtime and MQTT behavior](docs/runtime-behavior.md)
- [Architecture](docs/architecture.md) and [development guide](docs/development-guide.md)
- [Releasing to GitHub and Docker Hub](docs/releasing.md)
- [Changelog](CHANGELOG.md) and [security policy](.github/SECURITY.md)

MIT license; see [LICENSE](LICENSE).
