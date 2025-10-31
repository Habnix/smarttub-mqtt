# smarttub-mqtt

A robust MQTT bridge for SmartTub hot tubs providing extensive telemetry, control and error handling.

## Features

### 🌊 Spa Control & Monitoring
- **Read Topics**: Current status for heater, pumps, lights, sensors
- **Write Topics**: Control via MQTT using the `_writetopic` suffix
- **Meta Topics**: Self-documenting API with available commands
- **Multi-Spa Support**: Clean topic structure for multiple spas

### 🔄 Error Tracking & Recovery
- Centralized error collection across subsystems
- Automatic recovery strategies with callbacks
- Subsystem health monitoring (healthy / degraded / failed)
- MQTT meta topic for error status
- Web UI API for error management

### 📊 Discovery & Capability Detection
- Automatic spa detection on startup
- Capability probing for pumps, lights, heater
- **Systematic Light Mode Testing**: Tests all 18 light modes × 5 brightness levels
- Progress tracking with real-time MQTT updates
- YAML export of detected configuration
- See [Discovery Light Modes Guide](docs/discovery-light-modes.md)

### 🌐 Web UI
- Real-time dashboard with auto-refresh
- Spa status and controls
- Error log and subsystem status
- Discovery progress display
- Basic authentication (optional)

### 🔒 Security & Validation
- Comprehensive configuration validation
- Secure defaults for all parameters
- Type checking and range checks
- Basic auth with constant-time comparison
- OWASP Top 10 considerations

### 📝 Logging & Observability
- Structured JSON logging
- Log rotation with compression
- MQTT log publishing
- Heartbeat & telemetry
- Prometheus-ready metrics

## Quick Start

### Docker (Recommended)

```bash
# 1. Create configuration directory
mkdir -p /opt/smarttub-mqtt/config

# 2. Create .env file
cat > /opt/smarttub-mqtt/config/.env << EOF
SMARTTUB_EMAIL=user@example.com
SMARTTUB_PASSWORD=your_password
MQTT_BROKER_URL=mqtt://broker:1883
MQTT_USERNAME=mqttuser
MQTT_PASSWORD=mqttpass
EOF

# 3. Create smarttub.yaml (optional, for advanced configuration)
cat > /opt/smarttub-mqtt/config/smarttub.yaml << 'EOF'
smarttub:
  polling_interval_seconds: 30
mqtt:
  base_topic: smarttub-mqtt
  qos: 1
  retain: true
web:
  enabled: true
  port: 8080
logging:
  level: info
EOF

# 4. Start container
docker run -d \
  --name smarttub-mqtt \
  --restart unless-stopped \
  -v /opt/smarttub-mqtt/config:/config \
  -p 8080:8080 \
  smarttub-mqtt:latest
```

### Python

```bash
# 1. Clone repository
git clone https://github.com/your-org/smarttub-mqtt.git
cd smarttub-mqtt

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example config/.env
nano config/.env  # Add credentials

# 4. Start the bridge
python -m src.cli.run
```

## MQTT Topics

### Per-Spa Topics (Recommended)

```
smarttub-mqtt/
├── {spa_id}/
│   ├── heater/
│   │   ├── target_temperature          # Read: desired temperature
│   │   ├── target_temperature_writetopic  # Write: set desired temperature
│   │   ├── current_temperature         # Read: current temperature
│   │   └── meta                       # Meta: available commands
│   ├── pumps/
│   │   └── {pump_id}/
│   │       ├── state                  # Read: pump state
│   │       ├── state_writetopic       # Write: set pump state
│   │       └── meta                   # Meta: available commands
│   ├── lights/
│   │   └── {light_id}/
│   │       ├── state                  # Read: light state
│   │       ├── state_writetopic       # Write: set light state
│   │       ├── brightness             # Read: brightness
│   │       ├── brightness_writetopic  # Write: set brightness
│   │       └── meta                   # Meta: available commands
│   └── status/
│       ├── online                     # Read: online status
│       ├── water_temperature          # Read: water temperature
│       ├── ph                         # Read: pH value
│       └── orp                        # Read: ORP value
└── meta/
    ├── errors                         # Error summary & status
    └── discovery                      # Discovery progress
```

### Legacy Topics (Compatibility)

For backwards compatibility, topics without `{spa_id}` are also published (recommended only for single-spa setups).

### Write Topic Convention

**Read topics** show current value:
```
smarttub-mqtt/{spa_id}/heater/target_temperature → "40"
```

**Write topics** accept commands:
```
# Publish "42" to:
smarttub-mqtt/{spa_id}/heater/target_temperature_writetopic
```

**Meta topics** document the API:
```json
{
  "component": "heater",
  "writable_topics": {
    "target_temperature": {
      "topic": "smarttub-mqtt/{spa_id}/heater/target_temperature_writetopic",
      "type": "number",
      "min": 26,
      "max": 40,
      "unit": "°C"
    }
  }
}
```

## Command Execution & State Updates

### Timing & Latency

When an MQTT command is sent it follows these steps:

```
1. MQTT command received           (t=0s)
   ↓
2. POST request to SmartTub API   (~0.5s)
   ↓
3. Wait for API processing        (STATE_UPDATE_DELAY_SECONDS, default: 2.5s)
   ↓
4. GET request for new state     (~0.5s)
   ↓
5. MQTT state update published   (~3-4s total)
```

**Total latency**: ~3-4 seconds from command to state update

### State Update Delay configuration

The SmartTub Cloud API needs time to process commands. The `STATE_UPDATE_DELAY_SECONDS` parameter controls how long to wait after a command before polling for the new state.

**Via environment variable**:
```bash
# Default: 2.5 seconds (recommended for most spas)
STATE_UPDATE_DELAY_SECONDS=2.5

# Faster API: reduce delay
STATE_UPDATE_DELAY_SECONDS=1.5

# Slower API: increase delay
STATE_UPDATE_DELAY_SECONDS=4.0
```

**Via YAML config**:
```yaml
smarttub:
  state_update_delay_seconds: 2.5  # Range: 0.5 - 10.0
```

**When to adjust?**

- **Missing state updates**: increase delay (e.g. 3.5s)
- **Faster feedback desired**: reduce delay (e.g. 1.5s)
- **Different spas**: different spas may have different API latencies

**Note**: In addition to this immediate state fetch there is the regular polling (default every 30s, configurable via `POLL_INTERVAL`).

## Configuration

### Minimal (credentials only)

`/config/.env`:
```bash
SMARTTUB_EMAIL=user@example.com
SMARTTUB_PASSWORD=your_password
MQTT_BROKER_URL=mqtt://broker:1883
```

### Full (all options)

See [Configuration Guide](./docs/configuration.md) for:
- All parameters with defaults and validation
- MQTT TLS configuration
- Web UI basic auth
- Logging & rotation
- Safety & command verification
- Discovery & capability settings
- **State update timing** (STATE_UPDATE_DELAY_SECONDS)

## Web UI

Access at `http://localhost:8080`:

- **Dashboard**: spa status, temperature, pumps, lights
- **Control**: heater, pumps, lights control
- **Errors**: error log, subsystem status, clear function
- **Discovery**: progress tracking, component status
- **Logs**: live logs with filtering

### Basic Auth (optional)

```bash
WEB_AUTH_ENABLED=true
WEB_AUTH_USERNAME=admin
WEB_AUTH_PASSWORD=changeme
```

## Error Tracking

### MQTT Meta Topic

Subscribe to `smarttub-mqtt/meta/errors`:

```json
{
  "error_summary": {
    "total_errors": 5,
    "by_severity": {"error": 3, "warning": 2},
    "by_category": {"mqtt_connection": 2, "discovery": 3}
  },
  "subsystem_status": {
    "mqtt": "healthy",
    "discovery": "degraded",
    "web_ui": "healthy"
  }
}
```

### Web UI API

```bash
# Get errors
curl http://localhost:8080/api/errors

# Clear errors
curl -X POST http://localhost:8080/api/errors/clear?category=discovery
```

See [Error Tracking Guide](./docs/error-tracking.md) for details.

## Discovery

### Initial discovery

On first start:
1. Login to SmartTub API
2. Fetch all spas
3. Probe each spa (pumps, lights, heater, status)
4. Write YAML configuration
5. Publish MQTT topics

### Progress tracking

Subscribe to `smarttub-mqtt/meta/discovery`:

```json
{
  "overall_phase": "probing_spa",
  "total_spas": 1,
  "completed_spas": 0,
  "overall_percent": 45,
  "spas": {
    "spa123": {
      "spa_name": "Master Spa",
      "total_components": 5,
      "completed_components": 2,
      "progress_percent": 40,
      "current_component": {
        "component_type": "pump",
        "component_id": "pump_1",
        "phase": "probing_pumps"
      }
    }
  }
}
```

See [Discovery Progress Guide](./docs/discovery-progress.md) for details.

## Testing

```bash
# Unit tests
pytest tests/unit/ -v

# With coverage
pytest tests/unit/ --cov=src --cov-report=html

# Config validation only
pytest tests/unit/test_config_validation.py -v

# Error tracking only
pytest tests/unit/test_error_tracker.py -v
```

**Test coverage**:
- 58 tests for configuration validation
- 26 tests for error tracking
- 25 tests for discovery progress
- 109 tests total

See [Testing Guide](./docs/testing.md) for details.

## Development

```bash
# Setup
git clone https://github.com/your-org/smarttub-mqtt.git
cd smarttub-mqtt
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest

# Run with Docker
docker build -t smarttub-mqtt .
docker run -v $(pwd)/config:/config smarttub-mqtt

# Linting
ruff check .
```

## Architecture

```
src/
├── cli/           # CLI entry point
├── core/          # Core business logic
│   ├── config_loader.py        # Configuration & validation
│   ├── error_tracker.py        # Error tracking & recovery
│   ├── discovery_progress.py  # Discovery progress tracking
│   ├── smarttub_client.py      # SmartTub API client
│   └── item_prober.py          # Spa component probing
├── mqtt/          # MQTT integration
│   ├── broker_client.py        # MQTT connection & publishing
│   └── topic_mapper.py         # Topic structure & mapping
└── web/           # Web UI & API
    ├── app.py                  # FastAPI application
    └── auth.py                 # Basic authentication
```

## Documentation

- [Configuration Guide](./docs/configuration.md) - All parameters and validation
- [Error Tracking](./docs/error-tracking.md) - Error tracking and recovery
- [Discovery Progress](./docs/discovery-progress.md) - Discovery tracking
- [Security Review](./docs/security-review.md) - Security best practices
- [Testing Guide](./docs/testing.md) - Test strategy and coverage
- [WebUI Guide](./docs/webui.md) - Web interface
- [Logging Guide](./docs/logging.md) - Logging configuration

## Migration

### From version < 1.0

**Config path**: `/config/` instead of repository root

**Renamed parameters**:
- `max_size_mb` → `log_max_size_mb`
- `max_files` → `log_max_files`
- `dir` → `log_dir`

**New features**:
- Error tracking with recovery
- Discovery progress tracking
- Configuration validation
- Web UI with API

No breaking changes — older configurations remain supported.

## Client ID behavior

**Default**: auto-suffix to avoid collisions
```
smarttub-mqtt → smarttub-mqtt-1234
```

**Stable client ID** (for broker ACLs):
```yaml
mqtt:
  client_id: my-stable-client-id
```

Or via environment:
```bash
MQTT_CLIENT_ID=my-stable-client-id
```

## Troubleshooting

### Connection issues

```bash
# Check MQTT connection
docker logs smarttub-mqtt | grep mqtt

# Check error status
curl http://localhost:8080/api/errors
```

### Discovery problems

```bash
# Check discovery progress
curl http://localhost:8080/api/discovery/progress

# Force re-discovery
export CHECK_SMARTTUB=true
```

### Configuration errors

```bash
# Validate configuration
python -m src.core.config_loader /config/smarttub.yaml
```

## Support

- **Issues**: [GitHub Issues](https://github.com/your-org/smarttub-mqtt/issues)
- **Documentation**: [docs/](./docs/)
- **Tests**: `pytest tests/unit/ -v`

## License

[Your License Here]

## Contributing

Contributions welcome! See [CONTRIBUTING.md](./CONTRIBUTING.md).

---

**Status**: Production Ready ✅
**Version**: 1.0.0
**Last Updated**: October 30, 2025
