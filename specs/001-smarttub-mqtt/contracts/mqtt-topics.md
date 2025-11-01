# MQTT Topic Catalog: SmartTub MQTT Bridge

## Namespace

- **Base Prefix**: `smarttub-mqtt`
- Topics use `/` separators and hyphenated component identifiers (e.g., `heater-1`).
- Unless noted, QoS = 1 and retain = true for state topics.

## Telemetry Topics

| Topic | Direction | Payload | QoS | Retain | Notes |
|-------|-----------|---------|-----|--------|-------|
| `smarttub-mqtt/state/<component>/<metric>` | Publish | JSON `{ "value": <any>, "timestamp": iso8601 }` | 1 | true | Primary state feed per metric (e.g., temperature/currentTemp, status).
| `smarttub-mqtt/state/overview` | Publish | JSON `StateSnapshot` schema | 1 | false | Snapshot broadcast when significant change detected.
| `smarttub-mqtt/meta/capabilities` | Publish | JSON `CapabilityProfile` schema | 1 | true | Updated on discovery refresh.
| `smarttub-mqtt/meta/heartbeat` | Publish | JSON `{ "status": "ok", "timestamp": iso8601 }` | 0 | false | Emitted every 30s to signal service health.

## Command Topics

| Topic | Direction | Payload | QoS | Retain | Notes |
|-------|-----------|---------|-----|--------|-------|
| `smarttub-mqtt/command/<component>` | Subscribe | JSON `{ "action": str, "parameters": { ... } }` | 1 | false | Consumed from OpenHAB rules or MQTT items.
| `smarttub-mqtt/command/<component>/response` | Publish | JSON `{ "commandId": str, "status": str, "timestamp": iso8601, "message": str? }` | 1 | false | Confirmation or error feedback per command.
| `smarttub-mqtt/command/<component>/pending` | Publish | JSON `{ "commandId": str }` | 0 | false | Optional ephemeral indicator for UI progress spinners.

## Logging Topics

| Topic | Direction | Payload | QoS | Retain | Notes |
|-------|-----------|---------|-----|--------|-------|
| `smarttub-mqtt/meta/logs` | Publish | JSON `LogEvent` schema | 0 | false | Emitted only when MQTT log forwarding enabled.
| `smarttub-mqtt/meta/config` | Publish | JSON describing current config (poll interval, log level) | 0 | true | Helps remote observers validate config.

## Discovery Flow

1. On startup, publish `meta/capabilities` and `meta/config` retained messages.
2. For each supported command, publish retained schema hints on `smarttub-mqtt/meta/commands/<component>`.
3. OpenHAB listens to meta topics to dynamically create items; controls map to `command/<component>` topics.
4. When capability profile changes, re-publish meta topics and clear retired command topics via retained empty payloads.

## Error Handling

- If SmartTub API unavailable, publish `meta/heartbeat` with `status: "degraded"` and send log events at `ERROR` level.
- Command failures produce messages on `command/<component>/response` with `status: "FAILED"` and `message` details.
- Recovery sync after reconnect triggers full state snapshot on `state/overview` and component topics.
