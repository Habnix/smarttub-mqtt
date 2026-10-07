# SmartTub MQTT Bridge

MQTT bridge for SmartTub-enabled hot tubs, with a Web UI for status, controls,
errors and light-mode discovery. Works with an external MQTT broker and MQTT
consumers such as OpenHAB.

- Image: **`willnix/smarttub-mqtt`**
- Source and issues: [Habnix/smarttub-mqtt](https://github.com/Habnix/smarttub-mqtt)
- License: [MIT](https://github.com/Habnix/smarttub-mqtt/blob/main/LICENSE)
- Each instance connects to **one hot tub**.

## Tags and platforms

Public releases from 0.4.0 target Linux **AMD64** and **ARM64**.
Use the full version tag for predictable upgrades and rollbacks:

```bash
docker pull willnix/smarttub-mqtt:0.4.0
```

The examples below require the 0.4.0 release to have been published. Check the
[available tags](https://hub.docker.com/r/willnix/smarttub-mqtt/tags) first.

- `0.4.0`: this exact release.
- `0.4`: the newest published release in the 0.4 series.
- `latest`: the newest published stable release; it changes on release.
- The private Gitea `edge` image is for development and is not on Docker Hub.

Older tags can have different platform support; 0.3.3 supports AMD64 only.
Releases include image signatures, an SBOM and build provenance. The immutable
image digest and public verification key are published with the
[GitHub release](https://github.com/Habnix/smarttub-mqtt/releases).

## Requirements

- Docker Engine with Docker Compose.
- A working SmartTub account, using its email and password.
- A reachable MQTT broker. The image does not include a broker.
- Internet access from the container to the SmartTub cloud.

## Quick start with Docker Compose

Create a directory for the service, then create `config/` and `logs/` inside it:

```bash
mkdir -p config logs
```

Create `config/.env` with your own credentials:

```dotenv
SMARTTUB_EMAIL=you@example.com
SMARTTUB_PASSWORD='replace-with-your-smarttub-password'
MQTT_BROKER_URL=mqtt://192.168.1.100:1883
MQTT_USERNAME=your-mqtt-user
MQTT_PASSWORD='replace-with-your-mqtt-password'
DISCOVERY_MODE=off
```

Omit `MQTT_USERNAME` and `MQTT_PASSWORD` if your broker does not require them.
Use the broker's actual network address: `localhost` inside the container refers
to the container itself. Keep `.env` private and out of version control.

After saving `.env`, restrict its permissions. The image runs as UID **1000**;
on Linux, give that UID access to these dedicated service directories before
starting the container:

```bash
chmod 600 config/.env
sudo chown -R 1000:1000 config logs
```

Docker Desktop manages bind-mount permissions differently; the Linux ownership
command is usually unnecessary there. To edit the file later on Linux, use
`sudoedit config/.env` if your login user has a different UID.

Create `compose.yaml`:

```yaml
services:
  smarttub-mqtt:
    image: willnix/smarttub-mqtt:0.4.0
    container_name: smarttub-mqtt
    restart: unless-stopped
    env_file:
      - ./config/.env
    ports:
      - "8080:8080"
    volumes:
      - ./config:/config
      - ./logs:/logs
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Start and inspect the service:

```bash
docker compose up -d
docker compose logs -f smarttub-mqtt
```

Open `http://<docker-host>:8080` for the Web UI. On the Docker host itself,
use [localhost:8080](http://localhost:8080).

## Docker Run alternative

Use the same writable `config/` and `logs/` directories. Docker Run reads
`--env-file` values literally, unlike Compose's dotenv parsing. Create a
separate `docker-run.env` containing plain `KEY=value` entries, without enclosing
quotes or inline comments:

```dotenv
SMARTTUB_EMAIL=you@example.com
SMARTTUB_PASSWORD=replace-with-your-smarttub-password
MQTT_BROKER_URL=mqtt://192.168.1.100:1883
MQTT_USERNAME=your-mqtt-user
MQTT_PASSWORD=replace-with-your-mqtt-password
DISCOVERY_MODE=off
```

Replace the placeholders with your actual values. Include any additional
settings you use, and omit optional broker credentials when unnecessary.
Keep this file private too:

```bash
chmod 600 docker-run.env
```

```bash
docker run -d \
  --name smarttub-mqtt \
  --restart unless-stopped \
  --env-file ./docker-run.env \
  -p 8080:8080 \
  -v "$(pwd)/config:/config" \
  -v "$(pwd)/logs:/logs" \
  willnix/smarttub-mqtt:0.4.0
```

## Configuration

The [complete example configuration](https://github.com/Habnix/smarttub-mqtt/blob/v0.4.0/config/.env.example)
contains all environment options. Frequently used settings:

| Variable | Purpose | Default |
| --- | --- | --- |
| `SMARTTUB_EMAIL` | SmartTub account email | Required |
| `SMARTTUB_PASSWORD` | SmartTub account password | Required |
| `SMARTTUB_DEVICE_ID` | Select the hot tub explicitly | First device returned by the API |
| `MQTT_BROKER_URL` | External broker, e.g. `mqtt://broker:1883` | Required |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | Broker authentication | Optional |
| `MQTT_BASE_TOPIC` | MQTT topic prefix | `smarttub-mqtt` |
| `POLL_INTERVAL` | State polling interval in seconds | `30` |
| `DISCOVERY_MODE` | Startup light discovery: `off`, `startup_yaml`, `startup_quick`, `startup_full` | `off` |
| `WEB_AUTH_ENABLED` | Protect Web pages and device APIs with Basic Auth | `false` |
| `WEB_AUTH_USERNAME`, `WEB_AUTH_PASSWORD` | Web credentials when Basic Auth is enabled | Set your own |
| `LOG_LEVEL` | Log verbosity | `info` |

The current application selects one hot tub per running instance, even if the
account contains several devices. Monitoring and controlling several hot tubs
inside one container is not implemented. This is an application limitation;
several containers can share the same Docker host. Give each its own
`SMARTTUB_DEVICE_ID`, MQTT prefix, persistent directories and host port.

The Web UI is intended for a trusted home network. Enable Basic Auth outside
that boundary, and use a VPN or authenticated HTTPS proxy for remote access.
Do not forward port 8080 directly to the internet.

## Persistent data and health

- `/config`: local configuration and saved discovery/recovery data.
- `/logs`: application logs.
- `/live`: process liveness; used by Docker's built-in health check.
- `/ready`: dependency readiness, including MQTT and SmartTub connectivity.

A healthy process can temporarily have unavailable cloud or MQTT data. Inspect
`/ready`, the Web UI and logs when diagnosing connection problems.
Light-mode discovery changes the real lights during testing; start it deliberately
from the Web UI, and keep startup discovery off for normal daily use.

## Upgrade and rollback

Before upgrading from 0.3.3, back up `config/` and review the
[0.4.0 changelog](https://github.com/Habnix/smarttub-mqtt/blob/v0.4.0/CHANGELOG.md).
This release changes MQTT command results, pump/state metadata and configuration
handling; check existing OpenHAB items and MQTT consumers. Host Python is not
required; the new image includes Python 3.13.

For an upgrade, change the full version in `compose.yaml`, then run:

```bash
docker compose pull
docker compose up -d
docker compose logs --tail=100 smarttub-mqtt
```

For a rollback, stop the service, restore the backed-up `config/` if discovery
files were migrated, set the previous image tag, and run the same commands.
Check that the previous image supports your host architecture.

For support, include the image tag, architecture and redacted logs in a
[GitHub issue](https://github.com/Habnix/smarttub-mqtt/issues). Never include
passwords, tokens or your full `.env` file.
