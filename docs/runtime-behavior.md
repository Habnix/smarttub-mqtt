# Runtime and MQTT behavior

## Device selection

Each bridge instance selects one hot tub using `SMARTTUB_DEVICE_ID`, or the
first device returned by the SmartTub account when no ID is configured.
Polling, control, discovery and Web state use that selected device. MQTT
commands addressed to another device are rejected.

The previous public README advertised multiple hot tubs. The previous client
could retrieve all account devices, but its state reader and control methods
used only the first device. This was not complete support for multiple hot
tubs in one process. The current selection and routing guards make the single
device boundary explicit.

## Startup and configuration

The CLI loads configuration, connects to MQTT, initializes the SmartTub client,
publishes metadata and saved discovery data, subscribes to commands and starts
the Web UI. Capability detection, polling and capability refresh run when
`CHECK_SMARTTUB=true`. Setting it to `false` does not skip client initialization.

`--discover` runs discovery and then exits. `--show-discovery` displays saved
discovery results.

YAML configuration is optional. The CLI uses `--config FILE`, otherwise
`SMARTTUB_CONFIG` or `CONFIG_FILE`, otherwise defaults. Environment variables
override YAML values. Compose supplies them through `config/.env`; for local
CLI use, export them before starting:

```bash
set -a
source config/.env
set +a
python -m src.cli.run
```

## MQTT topics

The default topic layout is `smarttub-mqtt/<spa_id>/...`. `MQTT_BASE_TOPIC`
changes the prefix. Writable properties have a sibling ending in `_writetopic`:

```text
smarttub-mqtt/<spa_id>/heater/temperature
smarttub-mqtt/<spa_id>/filtration/mode
smarttub-mqtt/<spa_id>/filtration/mode_writetopic
smarttub-mqtt/<spa_id>/lights/zone_1/cycle_speed
smarttub-mqtt/<spa_id>/lights/zone_1/mode_writetopic
```

Filtration accepts `ECO_MODE` or `{"mode":"ECO_MODE"}`, and also supports
`NORMAL` and `NANO_MODE`. Light `cycle_speed` is read-only.

## State quality

Polling publishes each complete successful snapshot. If a cloud request fails,
the bridge preserves the last successful values and marks them stale instead
of inventing component states.

Retained `<base>/<spa_id>/availability` contains `online` after a successful
complete read and `offline` otherwise. Retained `state/quality` contains:

- `status`: `live`, `stale` or `unavailable`.
- `observed_at` and `last_success_at`: timestamps of the last successful read.
- `checked_at`: timestamp of the most recent quality check.

Before any successful read, `/api/state` returns `components: {}` with
unavailable quality.

Pump topics distinguish `state`, `speed`, `speed_capability` and role metadata.
For example, a two-speed pump running at LOW has `state=on`, `speed=low` and
`speed_capability=two_speed`. Unknown capabilities remain `unknown`. A pump
observed as off has `state=off` and `speed=off`.

## Command results

Web and MQTT commands receive a command ID. Subscribe to the non-retained
`<base>/<spa_id>/commands/result` topic for JSON containing `command_id`,
`command`, `status`, `message` and `timestamp`:

- `accepted`: validated and queued.
- `sent`: the SmartTub API call completed without a reported error.
- `confirmed`: a command-specific API read-back observed the requested state.
- `failed`: validation, component lookup or execution failed.
- `unknown`: sent, but the outcome could not be verified.

API confirmation does not guarantee a physical actuator response. Commands
without a specific read-back finish at `sent`.

Pump and light commands require a component ID. Prefer component-specific
topics; generic topics require an ID in JSON, such as
`{"state":"on","pump_id":"P1"}` or
`{"brightness":0,"light_id":"zone_1"}`. Binary pump control reads back after
each `toggle()` so that LOW → HIGH → OFF transitions can be handled correctly.

## Queues and reconnects

Commands use a serial queue, limited by `SAFETY_COMMAND_QUEUE_SIZE` (default
100), with `SAFETY_COMMAND_TIMEOUT_SECONDS` per command. When full, the Web API
returns HTTP 503 with `Retry-After`; MQTT receives a failed result.

MQTT publishes use `MQTT_PUBLISH_QUEUE_SIZE` (default 1000). During a disconnect,
retained values are merged per topic using the latest value. Non-retained
command results are buffered in order up to the configured limit; other
telemetry may be dropped under load. Reconnect restores subscriptions and
flushes buffered publishes. Shutdown drains the queue for up to
`MQTT_PUBLISH_DRAIN_TIMEOUT_SECONDS`.

Initial MQTT or cloud unavailability leaves Web diagnostics and reconnect
active. `<base>/status` is `degraded` until successful polling restores
`connected` status.

## Discovery and recovery

`DISCOVERY_MODE` accepts `off`, `startup_quick`, `startup_full` and
`startup_yaml`. With `off`, discovery can still be started manually through
Web or MQTT. Results are stored in `/config/discovered_items.yaml`.

Before changing a light zone, discovery saves its original state atomically
in `/config/discovery_recovery.yaml`. The entry is removed only after verified
restoration. An interrupted run must recover before another run starts;
otherwise the bridge asks for manual recovery.

Undocumented upstream calls are isolated in `SmartTubGateway` and checked
against `python-smarttub` 0.0.48. Production dependencies are pinned in
`requirements.lock`, including the upstream Git commit.

## Health endpoints

These endpoints remain accessible without Basic Authentication and omit
device and account details:

- `/live`: Web process and event loop respond; used by the Docker health check.
- `/ready`: MQTT, SmartTub, snapshot freshness and command worker are ready;
  otherwise returns HTTP 503.
- `/health`: compatibility alias for liveness.

Using liveness for the container health check allows temporary dependency
outages to recover without restart loops.
