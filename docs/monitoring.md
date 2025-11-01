# SmartTub MQTT Bridge - Monitoring Documentation

## Overview

The SmartTub MQTT Bridge monitors your SmartTub whirlpool state and publishes real-time telemetry to MQTT topics for integration with home automation systems like OpenHAB.

## Architecture

```
SmartTub API → SmartTubClient → StateManager → MQTTTopicMapper → MQTT Broker → OpenHAB
```

- **SmartTubClient**: Polls the SmartTub API every 30 seconds
- **StateManager**: Detects state changes and manages safe fallbacks
- **MQTTTopicMapper**: Publishes structured JSON payloads to MQTT topics
- **Web UI**: Provides real-time monitoring dashboard at `http://localhost:8080`

## MQTT Topics

### State Topics

All state topics follow the pattern: `{base_topic}/{component}/state`

Default base topic: `smarttub-mqtt`

#### Heater State
**Topic**: `smarttub-mqtt/heater/state`
```json
{
  "timestamp": "2023-10-25T10:00:00Z",
  "state": "on",
  "temperature": 38.5,
  "target_temperature": 39.0
}
```

#### Pump State
**Topic**: `smarttub-mqtt/pump/state`
```json
{
  "timestamp": "2023-10-25T10:00:00Z",
  "state": "running",
  "speed": "high"
}
```

#### Light State
**Topic**: `smarttub-mqtt/light/state`
```json
{
  "timestamp": "2023-10-25T10:00:00Z",
  "state": "on",
  "color": "blue",
  "brightness": 80
}
```

#### Spa System State
**Topic**: `smarttub-mqtt/spa/state`
```json
{
  "timestamp": "2023-10-25T10:00:00Z",
  "state": "ready",
  "water_temperature": 37.2,
  "air_temperature": 25.0
}
```

### MQTT Settings

- **QoS**: 1 (at least once delivery)
- **Retain**: true (topics persist for new subscribers)
- **Client ID**: `smarttub-mqtt-client` (configurable)

### Client ID behaviour

- By default the bridge uses the client id `smarttub-mqtt` with a process-unique
  suffix appended at runtime (for example `smarttub-mqtt-1234`). This prevents
  accidental client id collisions when starting multiple test runs or short‑lived
  one-shot invocations on the same host.
- If you explicitly set `mqtt.client_id` in `/config/smarttub.yaml` or the
  `MQTT_CLIENT_ID` environment variable, that value will be used without
  modification. Use that when you need a stable id for broker ACLs or tooling.

Examples:

```bash
# Explicit (stable) client id via env
export MQTT_CLIENT_ID="my-stable-client-id"

# Default behaviour (auto-suffix with PID)
python3 -m src.cli.run
```

## OpenHAB Integration

### Items Configuration

Add these items to your OpenHAB `items/smarttub.items` file:

```java
// Spa temperatures
Number SmartTub_Water_Temp "Water Temperature [%.1f °C]" <temperature> {mqtt="<[broker:smarttub-mqtt/spa/state:state:JSONPATH($.water_temperature)]"}
Number SmartTub_Air_Temp "Air Temperature [%.1f °C]" <temperature> {mqtt="<[broker:smarttub-mqtt/spa/state:state:JSONPATH($.air_temperature)]"}

// Heater
String SmartTub_Heater_State "Heater State" <heating> {mqtt="<[broker:smarttub-mqtt/heater/state:state:JSONPATH($.state)]"}
Number SmartTub_Heater_Temp "Heater Temperature [%.1f °C]" <temperature> {mqtt="<[broker:smarttub-mqtt/heater/state:state:JSONPATH($.temperature)]"}
Number SmartTub_Heater_Target "Heater Target [%.1f °C]" <temperature> {mqtt="<[broker:smarttub-mqtt/heater/state:state:JSONPATH($.target_temperature)]"}

// Pump
String SmartTub_Pump_State "Pump State" <flow> {mqtt="<[broker:smarttub-mqtt/pump/state:state:JSONPATH($.state)]"}
String SmartTub_Pump_Speed "Pump Speed" <flow> {mqtt="<[broker:smarttub-mqtt/pump/state:state:JSONPATH($.speed)]"}

// Lights
String SmartTub_Light_State "Light State" <light> {mqtt="<[broker:smarttub-mqtt/light/state:state:JSONPATH($.state)]"}
String SmartTub_Light_Color "Light Color" <light> {mqtt="<[broker:smarttub-mqtt/light/state:state:JSONPATH($.color)]"}
Number SmartTub_Light_Brightness "Light Brightness [%d %%]" <light> {mqtt="<[broker:smarttub-mqtt/light/state:state:JSONPATH($.brightness)]"}
```

### Sitemap Configuration

Add to your OpenHAB `sitemaps/default.sitemap`:

```java
sitemap default label="Home" {
    Frame label="SmartTub" {
        Text item=SmartTub_Water_Temp
        Text item=SmartTub_Air_Temp
        Text item=SmartTub_Heater_State
        Text item=SmartTub_Heater_Temp
        Text item=SmartTub_Heater_Target
        Text item=SmartTub_Pump_State
        Text item=SmartTub_Pump_Speed
        Text item=SmartTub_Light_State
        Text item=SmartTub_Light_Color
        Slider item=SmartTub_Light_Brightness
    }
}
```

## Web UI

The bridge provides a real-time monitoring dashboard at `http://localhost:8080`:

- **Live Status**: Current temperatures, states, and component status
- **Visual Indicators**: Color-coded status indicators and progress bars
- **Auto-refresh**: Updates every 30 seconds via HTMX
- **API Access**: REST endpoints available at `/api/state` and `/api/capabilities`

## Configuration

### Environment Variables

Create a `.env` file under `/config` (not committed to git) with your credentials; we provide an example at `config/.env.example`.

```bash
# SmartTub API
SMARTTUB_EMAIL=your-email@example.com
SMARTTUB_PASSWORD=your-password

# MQTT Broker
MQTT_BROKER_URL=mqtt://your-mqtt-broker:1883
MQTT_USERNAME=your-mqtt-username
MQTT_PASSWORD=your-mqtt-password
MQTT_BASE_TOPIC=smarttub-mqtt

# Web UI
WEB_HOST=0.0.0.0
WEB_PORT=8080
```

### YAML Configuration

Alternatively, configure via `/config/smarttub.yaml` (example provided at `config/smarttub.example.yaml`):

```yaml
smarttub:
  email: "your-email@example.com"
  password: "your-password"
  polling_interval_seconds: 30

mqtt:
  broker_url: "mqtt://your-mqtt-broker:1883"
  username: "your-mqtt-username"
  password: "your-mqtt-password"
  base_topic: "smarttub-mqtt"

web:
  host: "0.0.0.0"
  port: 8080
```

## Monitoring & Troubleshooting

### Health Checks

- **Web Health**: `GET http://localhost:8080/health`
- **API State**: `GET http://localhost:8080/api/state`
- **MQTT Logs**: Monitor MQTT topic `smarttub-mqtt/log` for structured logs

### Common Issues

1. **No MQTT Connection**: Check broker URL and credentials
2. **SmartTub API Errors**: Verify email/password, check SmartTub service status
3. **Missing Data**: Check polling interval, API rate limits
4. **Web UI Not Loading**: Verify port 8080 is available

### Logs

The bridge logs all operations to stdout in JSON format and forwards to MQTT:

```json
{"timestamp": "2023-10-25T10:00:00Z", "level": "info", "message": "state sync completed", "component_count": 4}
```

## Performance

- **Polling Interval**: 30 seconds (configurable)
- **State Sync Time**: < 5 seconds
- **Memory Usage**: ~50MB baseline
- **MQTT Messages**: 4-6 messages per polling cycle

## Security

- Credentials stored in `.env` file (not committed)
- MQTT authentication recommended
- Web UI authentication optional (configure `web.auth_enabled`)
- No external internet access required (local MQTT broker)