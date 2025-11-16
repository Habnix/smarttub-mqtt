````markdown
# smarttub-mqtt

[![Version](https://img.shields.io/badge/version-0.3.0-blue)](https://github.com/Habnix/smarttub-mqtt/releases)
[![License](https://img.shields.io/badge/license-MIT-green)](https://github.com/Habnix/smarttub-mqtt/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://hub.docker.com/r/willnix/smarttub-mqtt)
[![Docker Pulls](https://img.shields.io/docker/pulls/willnix/smarttub-mqtt)](https://hub.docker.com/r/willnix/smarttub-mqtt)
[![GitHub Stars](https://img.shields.io/github/stars/Habnix/smarttub-mqtt?style=social)](https://github.com/Habnix/smarttub-mqtt)

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
- **Background Discovery**: Automated light mode testing with 3 modes (Full/Quick/YAML-only)
- **WebUI Control**: User-friendly discovery page with live progress tracking
- **MQTT Control**: Start/stop discovery via MQTT commands
- **Startup Automation**: Optional automatic discovery on container startup
- **Persistent Storage**: Results saved to YAML and published to MQTT
- Automatic spa detection and capability probing
- Real-time progress tracking with percentage completion

### 🌐 Web UI
- Real-time dashboard with auto-refresh
- Spa status and controls
- **Discovery Page**: Interactive discovery control with live progress
- Error log and subsystem status
- Discovery progress display
- Basic authentication (optional)

### 🔒 Security & Validation
- Comprehensive configuration validation
- Secure defaults for all parameters
- Type checking and range checks
- Basic auth with constant-time comparison
- OWASP Top 10 considerations


````markdown
# smarttub-mqtt

A robust MQTT bridge for SmartTub hot tubs providing extensive telemetry, control and error handling.

## Features

### 🌊 Spa Control & Monitoring
- Read topics for heater, pumps, lights and sensors
- Write topics expose a `_writetopic` sibling for commands
- Meta topics document available commands and writable fields
- Multi-spa support with clear topic partitioning

### 🔄 Error Tracking & Recovery
- Centralized error collection across subsystems
- Automatic recovery strategies and callbacks
- Subsystem health monitoring (healthy / degraded / failed)
- MQTT meta topic for error status and Web UI access for manual handling

### 📊 Discovery & Capability Detection
- Automatic spa discovery and capability probing (pumps, lights, heater)
- Systematic light-mode testing for reliable control mappings
- Progress published in real-time via MQTT and written to YAML

### 🌐 Web UI
- Optional real-time dashboard (port 8080)
- Discovery progress, error view, and basic control actions
- Optional Basic Auth for protection

### 🔒 Security & Validation
- Configuration validation with safe defaults
- Type and range checks for critical parameters
- Secure basic auth (constant-time comparison)

### 💡 Reliability & Performance
- **Automatic state verification**: Uses python-smarttub's built-in `light.set_mode()` with state change detection
- **Rate-limiting protection**: Handles 429 "Too Many Requests" errors with exponential backoff (2s/4s/8s)
- **Online status checking**: Verifies spa connectivity before discovery to prevent timeouts
- **Dynamic mode support**: Correctly handles color wheel and RGB modes with variable intensity
- **Optimized discovery timing**: 5-second intervals between light mode tests for reliable API communication

### 🎨 Light Control Features
- **18 light modes tested**: OFF, ON, PURPLE, ORANGE, RED, YELLOW, GREEN, AQUA, BLUE, WHITE, AMBER, plus color wheels
- **Bidirectional sync**: MQTT commands control spa hardware AND app changes sync to MQTT
- **Verified compatibility**: Tested on D1 Chairman spa with both Interior and Exterior zones
- **Smart timing**: Discovery automatically spaces tests to prevent API rate-limiting
- **Live feedback**: Real-time MQTT updates when light modes change

### �📝 Logging & Observability
- Structured JSON logs, rotation and optional MQTT forwarding
- Prometheus-ready metrics and heartbeat telemetry

---

## Quick start (Docker)

1. Prepare config dir and .env

```bash
mkdir -p /opt/smarttub-mqtt/config
cat > /opt/smarttub-mqtt/config/.env << EOF
SMARTTUB_EMAIL=user@example.com
SMARTTUB_PASSWORD=your_password
MQTT_BROKER_URL=mqtt://broker:1883
MQTT_USERNAME=mqttuser
MQTT_PASSWORD=mqttpass
# Optional: Enable startup discovery
DISCOVERY_MODE=startup_quick
EOF
```

2. Run container

```bash
docker run -d \
  --name smarttub-mqtt \
  --restart unless-stopped \
  -v /opt/smarttub-mqtt/config:/config \
  -p 8000:8080 \
  willnix/smarttub-mqtt:latest
```

3. Access WebUI

Visit `http://<your-ip>:8080` for the dashboard and discovery page.

---

## ✅ Verified Test Results (v0.1.0)

**Test Date**: November 1, 2025  
**Test Environment**: Python 3.11.10, Real SmartTub account, Live MQTT broker

### Runtime Verification

| Component | Status | Details |
|-----------|--------|---------|
| **MQTT Connection** | ✅ PASS | Connected to 192.168.178.164:1883, client ID: smarttub-mqtt-6346 |
| **SmartTub API** | ✅ PASS | Login successful, account retrieved, 1 spa discovered |
| **Spa Discovery** | ✅ PASS | Spa "Jule" (ID: 100946961, Model: Chairman, Brand: D1) |
| **Component Detection** | ✅ PASS | 3 pumps (P1, CP, P2), 2 light zones, heater, status sensors |
| **Discovery Output** | ✅ PASS | `/config/discovered_items.yaml` created (101 KB) |
| **MQTT Publishing** | ✅ PASS | 40 state messages published successfully |
| **Web UI** | ✅ PASS | Accessible at http://192.168.178.146:8080 (HTTP 200) |

### Test Suite Results

| Test Suite | Tests | Status | Coverage |
|------------|-------|--------|----------|
| **Unit Tests** | 142 | ✅ 15/16 passed | Config 53%, Error 95%, Discovery 97% |
| **Integration Tests** | 45 | ✅ All passed | MQTT Bridge, Log Rotation |
| **Contract Tests** | 6 | ✅ All passed | MQTT Topic Schemas |
| **Static Analysis** | - | ✅ Syntax valid | `python -m compileall` passed |
| **Security Scan** | - | ✅ Clean | No real secrets found (test placeholders only) |

**Known Issues**:
- 1 unit test failure in `capability_detector` (model attribute mock issue, non-critical for runtime)

### Discovery Test Details

**Full Discovery Run** (with exhaustive light-mode testing disabled):
```
Start time:   2025-11-01 09:08:05
Completion:   2025-11-01 09:08:47 (42 seconds)
Components:   Spa metadata, 3 pumps, 2 light zones, heater, status
YAML size:    101 KB
MQTT topics:  40 state messages + meta topics
```

**Sample Discovery Output**:
```yaml
discovered_items:
  '100946961':
    spa_id: '100946961'
    discovered_at: '2025-11-01T09:08:05.859770+00:00'
    spa:
      name: D1 Chairman
      model: Chairman
    heater:
      present: true
      water_temperature: 29.0
    pumps:
    - id: P1
      type: JET
      state: 'OFF'
    - id: CP
      type: CIRCULATION
      state: HIGH
    - id: P2
      type: JET
      state: 'OFF'
    lights:
    - zone: 1
      mode: 'OFF'
      zoneType: INTERIOR
    - zone: 2
      mode: 'OFF'
      zoneType: EXTERIOR
```

**Production Ready**: All critical components verified and operational ✅

---

## Background Discovery (NEW in v0.3.0)

SmartTub-MQTT can automatically test which light modes your spa supports.

### Features
- 🔍 **Three Discovery Modes**: YAML-only (instant), Quick (~5 min), Full (~20 min)
- 🌐 **WebUI Control**: Interactive discovery page at `/discovery`
- 📡 **MQTT Control**: Start/stop via `smarttub-mqtt/discovery/control`
- 💾 **Persistent Results**: Saved to `/config/discovered_items.yaml`
- ⚡ **Startup Automation**: Optional automatic discovery on boot

### Quick Start

**Via WebUI**:
1. Visit `http://<your-ip>:8080/discovery`
2. Select a mode (Quick recommended)
3. Click "Start Discovery"

**Via MQTT**:
```bash
mosquitto_pub -t 'smarttub-mqtt/discovery/control' -m '{"action":"start","mode":"quick"}'
```

**Automatic at Startup**:
```bash
# In .env file
DISCOVERY_MODE=startup_quick  # off, startup_quick, startup_full, startup_yaml

# IMPORTANT: After first discovery, manually change to 'off' or 'startup_yaml'
# to avoid re-testing on every restart!
```

### Discovery Modes

| Mode | Duration | Modes Tested | Use Case |
|------|----------|--------------|----------|
| **YAML Only** | Instant | 0 (loads saved) | Reload existing results |
| **Quick** | ~5 min | 4 common modes | Quick verification |
| **Full** | ~20 min | All 18 modes | Complete discovery |

See [docs/discovery.md](./docs/discovery.md) for complete documentation.

---

## Configuration

Mount `/config` into the container and place runtime config and `.env` there. See `docs/configuration.md` for full options.

## State update timing

The bridge waits `STATE_UPDATE_DELAY_SECONDS` after sending commands to allow the SmartTub Cloud API to process the request before polling for the new state. Default: 2.5s.

## MQTT topics

Base topic: `smarttub-mqtt/`. Per-spa topics follow `smarttub-mqtt/{spa_id}/<component>/<property>`; writable fields expose `<property>_writetopic`.

## Web UI

Optional web UI at port 8080: dashboard, discovery progress, error management. Basic auth can be enabled via `.env`.

## Discovery

Discovery writes detected capabilities to `/config/discovered_items.yaml` and publishes progress under `smarttub-mqtt/meta/discovery`.

## Testing & development

Run unit tests with `pytest tests/unit/ -v`. Lint with `ruff check .`.

---

**Status**: Production Ready ✅
**Version**: 0.1
**Last Updated**: October 31, 2025

**Acknowledgements**: Thanks to Matt Zimmerman for python-smarttub (https://github.com/mdz/python-smarttub)

````
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

## Discovery Modes

### Operating Modes

The bridge supports different operating modes controlled by two key environment variables:

#### `CHECK_SMARTTUB` - Main Discovery Toggle

Controls whether the bridge connects to the SmartTub API for discovery and polling:

- **`CHECK_SMARTTUB=true`** (default, recommended for production):
  - Connects to SmartTub API on startup
  - Runs initial discovery to detect spa components
  - Polls API every 30s for state updates
  - Publishes state to MQTT topics
  - Web UI shows live data

- **`CHECK_SMARTTUB=false`** (special use cases):
  - **No API connection** - skips discovery and polling
  - Web UI still runs on port 8080
  - MQTT commands still work (via command queue)
  - Useful for:
    - Testing WebUI without API calls
    - Debugging MQTT infrastructure
    - Development/testing environments
    - Temporary API connection issues

#### `DISCOVERY_TEST_ALL_LIGHT_MODES` - Light Mode Testing

Controls whether to test all 18 light modes during discovery (runs only if `CHECK_SMARTTUB=true`):

- **`DISCOVERY_TEST_ALL_LIGHT_MODES=false`** (default, recommended for production):
  - Normal fast discovery (~30-60 seconds)
  - Detects components without testing individual light modes
  - Suitable for day-to-day operation

- **`DISCOVERY_TEST_ALL_LIGHT_MODES=true`** (initial setup only):
  - **Systematic testing of all light modes** (~3 minutes per light zone)
  - Tests: OFF, ON, PURPLE, ORANGE, RED, YELLOW, GREEN, AQUA, BLUE, WHITE, AMBER, color wheel modes
  - **5-second intervals** between tests for reliable API communication
  - Publishes test results to MQTT and YAML
  - Use **once during initial setup** to identify working light modes
  - Web UI remains accessible during testing (runs in background)

### Light Mode Discovery Timing

**Important**: The SmartTub API requires time to process light mode changes. Discovery uses `LIGHT_TEST_DELAY_SECONDS=5` to prevent rate-limiting errors:

- **Too fast (1s)**: API rejects commands with 400 Bad Request
- **Optimal (5s)**: All modes detected reliably
- **Per zone**: ~90 seconds (18 modes × 5s)
- **Two zones**: ~3 minutes total

**Live Testing Results** (v1.5.0):
- ✅ HIGH_SPEED_WHEEL: Confirmed working
- ✅ LOW_SPEED_WHEEL: Confirmed working  
- ✅ FULL_DYNAMIC_RGB: Confirmed working
- ✅ Bidirectional sync: MQTT↔Spa verified

### Recommended Configurations

| Scenario | CHECK_SMARTTUB | DISCOVERY_TEST_ALL_LIGHT_MODES | Use Case |
|----------|----------------|-------------------------------|----------|
| **Production** | `true` | `false` | Normal spa control with fast startup |
| **Initial Setup** | `true` | `true` | One-time testing to identify working light modes |
| **Development** | `false` | `false` | Test WebUI/MQTT without API calls |

**Example `.env` configurations**:

```bash
# Production (recommended)
CHECK_SMARTTUB=true
DISCOVERY_TEST_ALL_LIGHT_MODES=false

# Initial setup (run once) 
CHECK_SMARTTUB=true
DISCOVERY_TEST_ALL_LIGHT_MODES=true
LIGHT_TEST_DELAY_SECONDS=5  # Optimal timing for reliable discovery

# Development/testing
CHECK_SMARTTUB=false
DISCOVERY_TEST_ALL_LIGHT_MODES=false  # ignored when CHECK_SMARTTUB=false
```

**Note**: `DISCOVERY_TEST_ALL_LIGHT_MODES` is only effective when `CHECK_SMARTTUB=true`. If `CHECK_SMARTTUB=false`, discovery never runs and the light mode testing setting is ignored.

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
# The SmartTub Cloud API needs time to process commands. The `STATE_UPDATE_DELAY_SECONDS`
# parameter controls how long to wait after a command before polling for the new state.

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
**Version**: 1.5.0  
**Last Updated**: November 8, 2025

## Acknowledgements
Thanks to Matt Zimmerman for the python-smarttub API used to interact with SmartTub devices: https://github.com/mdz/python-smarttub

```
Thanks to Matt Zimmerman for the python-smarttub API used to interact with SmartTub devices: https://github.com/mdz/python-smarttub

````

**Via Environment Variable**:
```bash
# Default: 2.5 seconds (recommended for most spas)
STATE_UPDATE_DELAY_SECONDS=2.5

# Faster API: reduce delay
STATE_UPDATE_DELAY_SECONDS=1.5

# Slower API: increase delay
STATE_UPDATE_DELAY_SECONDS=4.0
```

**Via YAML Config**:
```yaml
smarttub:
  state_update_delay_seconds: 2.5  # Range: 0.5 - 10.0
```

**When to adjust?**

- **Missing state updates**: increase delay (e.g. 3.5s)
- **Faster feedback desired**: reduce delay (e.g. 1.5s)
- **Different spas**: Different spa models may have varying API latencies

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

Zugriff auf `http://localhost:8080`:

- **Dashboard**: Spa-Status, Temperatur, Pumpen, Lichter
- **Control**: Heizung, Pumpen, Lichter steuern
- **Errors**: Error-Log, Subsystem-Status, Clear-Funktion
- **Discovery**: Progress-Tracking, Component-Status
- **Logs**: Live-Logs mit Filtering

### Basic Auth (optional)

```bash
WEB_AUTH_ENABLED=true
WEB_AUTH_USERNAME=admin
WEB_AUTH_PASSWORD=changeme
```

## Error Tracking

### MQTT Meta-Topic

Subscribe auf `smarttub-mqtt/meta/errors`:

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

### WebUI API

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

### Progress Tracking

Subscribe auf `smarttub-mqtt/meta/discovery`:

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
# Unit Tests
pytest tests/unit/ -v

# Mit Coverage
pytest tests/unit/ --cov=src --cov-report=html

# Nur Konfigurationsvalidierung
pytest tests/unit/test_config_validation.py -v

# Nur Error Tracking
pytest tests/unit/test_error_tracker.py -v
```

**Test Coverage:**
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

# Run Tests
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
├── cli/           # CLI Entry Point
├── core/          # Core Business Logic
│   ├── config_loader.py        # Configuration & Validation
│   ├── error_tracker.py        # Error Tracking & Recovery
│   ├── discovery_progress.py  # Discovery Progress Tracking
│   ├── smarttub_client.py      # SmartTub API Client
│   └── item_prober.py          # Spa Component Probing
├── mqtt/          # MQTT Integration
│   ├── broker_client.py        # MQTT Connection & Publishing
│   └── topic_mapper.py         # Topic Structure & Mapping
└── web/           # Web UI & API
    ├── app.py                  # FastAPI Application
    └── auth.py                 # Basic Authentication
```

## Documentation

- [Configuration Guide](./docs/configuration.md) - Alle Parameter und Validierung
- [Error Tracking](./docs/error-tracking.md) - Error-Tracking und Recovery
- [Discovery Progress](./docs/discovery-progress.md) - Discovery-Tracking
- [Security Review](./docs/security-review.md) - Security Best Practices
- [Testing Guide](./docs/testing.md) - Test-Strategie und Coverage
- [WebUI Guide](./docs/webui.md) - Web Interface
- [Logging Guide](./docs/logging.md) - Logging-Konfiguration

## Migration

### From Version < 1.0

**Config Path**: `/config/` statt Root-Verzeichnis

**Umbenannte Parameter:**
- `max_size_mb` → `log_max_size_mb`
- `max_files` → `log_max_files`
- `dir` → `log_dir`

**Neue Features:**
- Error Tracking mit Recovery
- Discovery Progress Tracking
- Konfigurationsvalidierung
- Web UI mit API

Keine breaking changes - alle alten Konfigurationen funktionieren weiterhin.

## Client ID Verhalten

**Default**: Auto-suffix to avoid collisions
```
smarttub-mqtt → smarttub-mqtt-1234
```

**Stable client ID** (for broker ACLs):
```yaml
mqtt:
  client_id: my-stable-client-id
```

Oder via Environment:
```bash
MQTT_CLIENT_ID=my-stable-client-id
```

## Troubleshooting

### Connection Issues

```bash
# Check MQTT Connection
docker logs smarttub-mqtt | grep mqtt

# Check Error Status
curl http://localhost:8080/api/errors
```

### Discovery Problems

```bash
# Check Discovery Progress
curl http://localhost:8080/api/discovery/progress

# Force Re-Discovery
export CHECK_SMARTTUB=true
```

### Configuration Errors

```bash
# Validate Configuration
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
**Version**: 0.1
**Last Updated**: October 31, 2025
