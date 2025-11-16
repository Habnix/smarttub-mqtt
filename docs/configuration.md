# Configuration Guide

**Status**: Complete ✅ (T062)

## Overview

SmartTub-MQTT supports flexible configuration via YAML files and environment variables. All parameters are validated and have safe defaults.

## Configuration sources

### Priority (highest first)

1. **Environment variables** (in `/config/.env`)
2. **YAML configuration** (`/config/smarttub.yaml`)
3. **Defaults** (defined in code)

### Recommended layout

```
/config/
├── .env                  # Secrets (do not commit)
└── smarttub.yaml         # Base configuration
```

## SmartTub API Configuration

### Required Parameters

```yaml
smarttub:
  email: user@example.com      # SmartTub Account Email (REQUIRED)
  password: secret123          # OR token (einer von beiden REQUIRED)
  token: abc123token          # Alternative zu password
```

**Umgebungsvariablen:**
```bash
````markdown
# Configuration Guide

**Status**: Complete ✅ (T062)

## Overview

SmartTub-MQTT supports flexible configuration via YAML files and environment variables. All parameters are validated and have safe defaults.

## Configuration sources

### Priority (highest first)

1. **Environment variables** (in `/config/.env`)
2. **YAML configuration** (`/config/smarttub.yaml`)
3. **Defaults** (defined in code)

### Recommended layout

```
/config/
├── .env                  # Secrets (do not commit)
└── smarttub.yaml         # Base configuration
```

## SmartTub API configuration

### Required parameters

```yaml
smarttub:
  email: user@example.com      # SmartTub account email (REQUIRED)
  password: secret123          # OR token (one of them REQUIRED)
  token: abc123token           # Alternative to password
```

**Environment variables:**
```bash
SMARTTUB_EMAIL=user@example.com
SMARTTUB_PASSWORD=secret123
# SMARTTUB_DEVICE_ID=  # Optional: auto-detected
```

### Optional parameters

| Parameter | Default | Min | Description |
|-----------|---------|-----|-------------|
| `device_id` | Auto-detect | - | SmartTub device id |
| `polling_interval_seconds` | 30 | 1 | API polling interval |
| `poll_min_interval_seconds` | 5 | 1 | Minimum time between polls |
| `state_update_delay_seconds` | 2.5 | 0.5-10.0 | Delay after a command before reading state |
| `max_retries` | 2 | 0 | Number of retries on error |
| `retry_backoff_seconds` | 5 | 1 | Wait between retries |

**State update delay details**

`state_update_delay_seconds` controls the wait time after an MQTT command before querying the SmartTub Cloud API for the updated state.

- Default: 2.5 seconds (recommended)
- Range: 0.5 to 10.0 seconds
- Purpose: SmartTub Cloud API needs time to process commands
- Tuning:
  - Increase (e.g. 3.5s) when state updates are missing
  - Decrease (e.g. 1.5s) for faster response
  - Varies by spa model and cloud latency

**Validation:**
- `poll_min_interval_seconds` ≤ `polling_interval_seconds`
- `state_update_delay_seconds` between 0.5 and 10.0
- One of `password` or `token` must be set

## MQTT configuration

### Required parameters

```yaml
mqtt:
  broker_url: mqtt://localhost:1883  # MQTT broker URL (REQUIRED)
```

**Environment variables:**
```bash
MQTT_BROKER_URL=mqtt://localhost:1883
MQTT_USERNAME=user
MQTT_PASSWORD=pass
MQTT_BASE_TOPIC=smarttub-mqtt
```

### Optional parameters

| Parameter | Default | Min/Max | Description |
|-----------|---------|---------|-------------|
| `username` | None | - | MQTT auth username |
| `password` | None | - | MQTT auth password |
| `client_id` | `smarttub-mqtt` | - | MQTT client id |
| `base_topic` | `smarttub-mqtt` | - | MQTT base topic |
| `qos` | 1 | 0-2 | Quality of service |
| `retain` | true | - | Retain messages |
| `keepalive` | 60 | 10+ | Keepalive interval (seconds) |

### TLS configuration

```yaml
mqtt:
  tls:
    enabled: false
    ca_cert_path: /path/to/ca.crt
```

**Validation:**
- `qos` must be 0..2
- `keepalive` at least 10 seconds

## Web UI configuration

### Parameters

```yaml
web:
  enabled: true         # Enable Web UI
  host: 0.0.0.0         # Listen address
  port: 8080            # Listen port
```

**Environment variables:**
```bash
WEB_ENABLED=true
WEB_HOST=0.0.0.0
WEB_PORT=8080

# Basic authentication
WEB_AUTH_ENABLED=false
WEB_AUTH_USERNAME=admin
WEB_AUTH_PASSWORD=changeme
```

**Validation:**
- `port` must be between 1 and 65535

### Web UI refresh

```yaml
web_ui:
  refresh_interval_seconds: 5  # UI auto-refresh interval
```

**Min:** 1 second

## Logging configuration

### Parameters

```yaml
logging:
  level: info                           # Log level
  log_dir: /logs                       # Log directory (Docker: /logs, Standalone: /var/log/smarttub-mqtt)
  log_max_size_mb: 5                   # Max file size before rotation
  log_max_files: 5                     # Max rotated files to keep
  log_compress: true                   # Compress rotated logs
  mqtt_log_enabled: true               # Publish logs to MQTT
  mqtt_log_level: warning              # Min level for MQTT logs
  mqtt_forwarding: false               # Forward all logs to MQTT
  stdout_format: json                  # Console output format
  file_path: null                      # Custom log file path
```

**Environment variables:**
```bash
LOG_LEVEL=info
# Docker (with volume mapping ./logs:/logs)
LOG_DIR=/logs
# Standalone installation
# LOG_DIR=/var/log/smarttub-mqtt

LOG_MAX_SIZE_MB=5
LOG_MAX_FILES=5
LOG_COMPRESS=true
LOG_MQTT_ENABLED=true
LOG_MQTT_LEVEL=warning
```

### Valid log levels

- `trace` (very verbose)
- `debug` (development)
- `info` (default)
- `warning`
- `error`
- `critical`

**Validation:**
- `log_max_size_mb` at least 1 MB
- `log_max_files` at least 1
- `level` and `mqtt_log_level` must be valid levels

## Safety configuration

### Command safety

```yaml
safety:
  fail_safe_mode: stop_pumps           # Failsafe behavior
  command_timeout_seconds: 7           # Command execution timeout
  post_command_wait_seconds: 12        # Wait after command
  command_verification_retries: 3      # Verification attempts
  command_max_retries: 2               # Max command retries
```

**Environment variables:**
```bash
SAFETY_POST_COMMAND_WAIT_SECONDS=12
SAFETY_COMMAND_VERIFICATION_RETRIES=3
SAFETY_COMMAND_TIMEOUT_SECONDS=7
SAFETY_COMMAND_MAX_RETRIES=2
```

**Validation:**
- `command_timeout_seconds` must be positive
- `post_command_wait_seconds` at least 1 second
- `command_verification_retries` and `command_max_retries` >= 0

## Discovery & capability configuration

### Discovery settings

```yaml
capability:
  cache_expiry_seconds: 3600           # Capability cache lifetime
  refresh_interval_seconds: 300        # Capability refresh interval
  discovery_refresh_interval: 3600     # Full discovery interval
  enable_auto_discovery: true          # Auto-discover on startup
  perform_destructive_probes: false    # Dangerous probe operations
```

**Environment variables:**
```bash
CHECK_SMARTTUB=true                      # Enables discovery on startup
DISCOVERY_REFRESH_INTERVAL=3600
CAPABILITY_REFRESH_INTERVAL=300
DISCOVERY_TEST_ALL_LIGHT_MODES=true     # Enables systematic light mode testing
```

**Light mode discovery:**

The `DISCOVERY_TEST_ALL_LIGHT_MODES` option enables systematic testing of all available light modes:

- Tests **all 18 light modes** × **5 brightness levels** (0%, 25%, 50%, 75%, 100%)
- Duration: ~30 minutes per light zone
- Output: YAML file with all working mode/brightness combinations
- See [Discovery Light Modes Guide](discovery-light-modes.md) for details

**Validation:**
- `cache_expiry_seconds` at least 60 seconds
- `refresh_interval_seconds` at least 60 seconds
- `discovery_refresh_interval` at least 300 seconds

## Observability configuration

### Heartbeat & telemetry

```yaml
observability:
  heartbeat_interval_seconds: 30   # Heartbeat publish interval
  telemetry_batch_size: 10        # Events per batch
```

**Validation:**
- Both values must be positive

## Docker configuration

### Container settings

```yaml
docker:
  health_check_interval_seconds: 30    # Health check interval
  graceful_shutdown_timeout_seconds: 30 # Shutdown timeout
```

**Validation:**
- Both values must be positive

## Complete example

### `/config/smarttub.yaml`

```yaml
# SmartTub API
smarttub:
  email: user@example.com
  polling_interval_seconds: 30
  poll_min_interval_seconds: 5
  max_retries: 2
  retry_backoff_seconds: 5

# MQTT Broker
mqtt:
  broker_url: mqtt://broker:1883
  client_id: smarttub-mqtt
  base_topic: smarttub-mqtt
  qos: 1
  retain: true
  keepalive: 60
  tls:
    enabled: false

# Web UI
web:
  enabled: true
  host: 0.0.0.0
  port: 8080

web_ui:
  refresh_interval_seconds: 5

# Logging
logging:
  level: info
  log_dir: /logs
  log_max_size_mb: 5
  log_max_files: 5
  log_compress: true
  mqtt_log_enabled: true
  mqtt_log_level: warning

# Safety
safety:
  fail_safe_mode: stop_pumps
  command_timeout_seconds: 7
  post_command_wait_seconds: 12
  command_verification_retries: 3
  command_max_retries: 2

# Discovery
capability:
  cache_expiry_seconds: 3600
  refresh_interval_seconds: 300
  discovery_refresh_interval: 3600
  enable_auto_discovery: true
  perform_destructive_probes: false

# Observability
observability:
  heartbeat_interval_seconds: 30
  telemetry_batch_size: 10

# Docker
docker:
  health_check_interval_seconds: 30
  graceful_shutdown_timeout_seconds: 30
```

### `/config/.env`

```bash
# SmartTub credentials (REQUIRED)
SMARTTUB_EMAIL=user@example.com
SMARTTUB_PASSWORD=secret123

# MQTT credentials
MQTT_BROKER_URL=mqtt://broker:1883
MQTT_USERNAME=mqttuser
MQTT_PASSWORD=mqttpass
MQTT_BASE_TOPIC=smarttub-mqtt

# Web UI auth
WEB_AUTH_ENABLED=true
WEB_AUTH_USERNAME=admin
WEB_AUTH_PASSWORD=changeme

# Discovery
CHECK_SMARTTUB=true
DISCOVERY_REFRESH_INTERVAL=3600
CAPABILITY_REFRESH_INTERVAL=300

# Logging
LOG_LEVEL=info
LOG_DIR=/logs
```

## Environment variable override

Environment variables override YAML values:

```bash
# Override values defined in YAML
export SMARTTUB_EMAIL=different@example.com
export MQTT_BROKER_URL=mqtt://different-broker:1883
export LOG_LEVEL=debug
```

## Validation

### Automatic validation

All configuration parameters are validated at load time:

```python
from src.core.config_loader import load_config, ConfigError

try:
    config = load_config("/config/smarttub.yaml")
except ConfigError as e:
    print(f"Configuration error: {e}")
    sys.exit(1)
```

### Error messages

Clear, actionable error messages:

```
ConfigError: smarttub.email is required
ConfigError: mqtt.qos must be between 0 and 2
ConfigError: web.port must be between 1 and 65535
ConfigError: smarttub.poll_min_interval_seconds cannot be greater than polling_interval_seconds
ConfigError: logging.level must be one of ['critical', 'debug', 'error', 'info', 'trace', 'warning']
```

## Testing

See `tests/unit/test_config_validation.py` for 58 comprehensive validation tests.

## Migration guide

### From versions < 1.0

1. **YAML path change**: configs are now under `/config/` instead of the repo root
2. **New parameters**: see the complete example above
3. **Renamed parameters**:
   - `max_size_mb` → `log_max_size_mb`
   - `max_files` → `log_max_files`
   - `dir` → `log_dir`

### Breaking changes

No breaking changes - parameters have defaults and remain backward compatible.

## Related

- [Error Tracking](./error-tracking.md)
- [Discovery Progress](./discovery-progress.md)
- [Security](./security-review.md)
- [Testing](./testing.md)

````
