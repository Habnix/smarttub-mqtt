# Error Tracking and Recovery

**Status**: Implemented ✅ (T058)

## Overview

The error tracking system provides centralized error collection, automatic recovery strategies, and comprehensive error analysis across all subsystems.

## Architecture

### Components

- **ErrorTracker** (`src/core/error_tracker.py`): central tracking class
- **MQTT meta topic**: `{base_topic}/meta/errors` (JSON, retained, QoS 1)
- **Web UI API**: `/api/errors` (GET), `/api/errors/clear` (POST)
- **Integration**: all subsystems (MQTT, discovery, Web UI, CLI, state)

### Error Categories

```python
class ErrorCategory(Enum):
    DISCOVERY = "discovery"
    YAML_PARSING = "yaml_parsing"
    MQTT_CONNECTION = "mqtt_connection"
    MQTT_PUBLISH = "mqtt_publish"
    LOGGING_SYSTEM = "logging_system"
    SMARTTUB_API = "smarttub_api"
    CONFIGURATION = "configuration"
    WEB_UI = "web_ui"
    COMMAND_EXECUTION = "command_execution"
    STATE_SYNC = "state_sync"
```

### Severity Levels

```python
class ErrorSeverity(Enum):
    INFO = "info"          # Informational
    WARNING = "warning"    # Non-critical issue
    ERROR = "error"        # Recoverable error
    CRITICAL = "critical"  # System failure
```

## Usage

### Tracking Errors

```python
from src.core.error_tracker import ErrorTracker, ErrorSeverity, ErrorCategory

tracker = ErrorTracker(max_errors=100)

# Track simple error
tracker.track_error(
    category=ErrorCategory.MQTT_CONNECTION,
    severity=ErrorSeverity.ERROR,
    message="Connection lost to broker",
    details={"broker": "mqtt://broker:1883"}
)

# Track error with recovery
tracker.track_error(
    category=ErrorCategory.DISCOVERY,
    severity=ErrorSeverity.WARNING,
    message="Failed to probe spa",
    details={"spa_id": "spa123"},
    recoverable=True
)
```

### Registering Recovery Callbacks

```python
def recover_mqtt_connection(error_entry):
    """Recovery callback for MQTT connection errors"""
    try:
        # Reconnect logic
        broker.reconnect()
        return True
    except Exception as e:
        logger.error(f"Recovery failed: {e}")
        return False

tracker.register_recovery_callback(
    ErrorCategory.MQTT_CONNECTION,
    recover_mqtt_connection
)
```

### Querying Errors

```python
# Get all errors
all_errors = tracker.get_errors()

# Get errors by category
mqtt_errors = tracker.get_errors(category=ErrorCategory.MQTT_CONNECTION)

# Get errors by severity
critical = tracker.get_errors(severity=ErrorSeverity.CRITICAL)

# Get error summary
summary = tracker.get_error_summary()
# Returns:
# {
#   "total_errors": 42,
#   "by_severity": {"error": 30, "warning": 10, "critical": 2},
#   "by_category": {"mqtt_connection": 15, "discovery": 12, ...},
#   "recent_errors": [...]  # Last 10 errors
# }

# Get subsystem status
status = tracker.get_subsystem_status()
# Returns: {"mqtt": "healthy", "discovery": "degraded", ...}
```

### Clearing Errors

```python
# Clear all errors
tracker.clear_errors()

# Clear errors by category
tracker.clear_errors(category=ErrorCategory.DISCOVERY)
```

## MQTT Meta-Topic

### Topic Structure

```
smarttub-mqtt/meta/errors
```

### Payload Example

```json
{
  "error_summary": {
    "total_errors": 5,
    "by_severity": {
      "error": 3,
      "warning": 2
    },
    "by_category": {
      "mqtt_connection": 2,
      "discovery": 3
    },
    "recent_errors": [
      {
        "timestamp": "2025-01-08T10:30:00Z",
        "category": "discovery",
        "severity": "error",
        "message": "Failed to probe spa",
        "details": {"spa_id": "spa123"}
      }
    ]
  },
  "subsystem_status": {
    "mqtt": "healthy",
    "discovery": "degraded",
    "web_ui": "healthy",
    "smarttub_api": "healthy",
    "state_sync": "healthy"
  }
}
```

### Publishing

- **Automatically on errors**: After each `track_error()` call
- **Periodically**: Every 10 polling iterations
- **Initial**: On startup
- **Retained**: Yes (OpenHAB sees the current status immediately)
- **QoS**: 1 (At least once delivery)

## WebUI API

### GET /api/errors

Returns error summary and subsystem status.

**Response:**
```json
{
  "error_summary": {...},
  "subsystem_status": {...}
}
```

### POST /api/errors/clear

Clears errors (all or by category).

**Query Parameters:**
- `category` (optional): Error category to clear

**Response:**
```json
{
  "cleared": 5,
  "category": "discovery"
}
```

## Integration

### MQTT broker client

```python
from src.mqtt.broker_client import MQTTBrokerClient
from src.core.error_tracker import ErrorTracker

tracker = ErrorTracker()
broker = MQTTBrokerClient(config, error_tracker=tracker)

# Automatically tracks:
# - publish errors (MQTT_PUBLISH)
# - connection loss (MQTT_CONNECTION)
# - reconnect errors (MQTT_CONNECTION)
```

### Discovery (ItemProber)

```python
from src.core.item_prober import ItemProber

prober = ItemProber(config, broker, error_tracker=tracker)

# Automatically tracks:
# - discovery probe errors (DISCOVERY)
# - YAML serialization/write errors (YAML_PARSING)
# - file write errors (YAML_PARSING)
```

### WebUI

```python
from src.web.app import create_app

app = create_app(config, error_tracker=tracker)

# Automatically provides:
# - GET /api/errors
# - POST /api/errors/clear
```

### CLI

```python
# src/cli/run.py creates ErrorTracker and distributes it
tracker = ErrorTracker(max_errors=100)

# Passed to:
broker = MQTTBrokerClient(config, error_tracker=tracker)
prober = ItemProber(config, broker, error_tracker=tracker)
app = create_app(config, error_tracker=tracker)
```

## Subsystem Health Status

### Status Types

- **healthy**: Keine Errors in letzten 5 Minuten
- **degraded**: Warnings oder Errors in letzten 5 Minuten
- **failed**: Critical Errors in letzten 5 Minuten

### Subsystem Mapping

```python
SUBSYSTEM_CATEGORIES = {
    "mqtt": [ErrorCategory.MQTT_CONNECTION, ErrorCategory.MQTT_PUBLISH],
    "discovery": [ErrorCategory.DISCOVERY],
    "smarttub_api": [ErrorCategory.SMARTTUB_API],
    "web_ui": [ErrorCategory.WEB_UI],
    "configuration": [ErrorCategory.CONFIGURATION],
    "state_sync": [ErrorCategory.STATE_SYNC]
}
```

## Recovery Strategies

### Automatic Recovery

```python
# Track error with recovery flag
tracker.track_error(
    category=ErrorCategory.MQTT_CONNECTION,
    severity=ErrorSeverity.ERROR,
    message="Connection lost",
    recoverable=True  # Triggers automatic recovery
)

# Recovery callback is called automatically
# Recovery state is tracked in error_entry
```

### Manual Recovery

```python
# Get error entry
errors = tracker.get_errors(category=ErrorCategory.MQTT_CONNECTION)
error_entry = errors[0]

# Attempt recovery
success = tracker.attempt_recovery(error_entry)
if success:
    print("Recovery successful")
else:
    print("Recovery failed")
```

## Thread safety

All ErrorTracker operations are thread-safe via internal locks.

```python
# Safe from multiple threads
tracker.track_error(...)  # Thread-safe
tracker.get_errors()      # Thread-safe
tracker.clear_errors()    # Thread-safe
```

## Storage

-- **Max errors**: configurable (default: 100)
-- **FIFO**: oldest errors are automatically removed
-- **In-memory**: no persistence (cleared on restart)

## Best Practices

1. **Use Appropriate Severity**:
  - INFO: Informational (e.g., "Discovery started")
  - WARNING: Non-critical (e.g., "Slow response from API")
  - ERROR: Recoverable (e.g., "Connection lost, retrying")
  - CRITICAL: System failure (e.g., "Configuration invalid")

2. **Provide Details**:
   ```python
   tracker.track_error(
       category=ErrorCategory.DISCOVERY,
       severity=ErrorSeverity.ERROR,
       message="Failed to probe spa",
       details={
           "spa_id": "spa123",
           "error": str(e),
           "attempt": 3
       }
   )
   ```

3. **Register Recovery Callbacks**:
   ```python
   # Early in initialization
   tracker.register_recovery_callback(
       ErrorCategory.MQTT_CONNECTION,
       recover_mqtt_connection
   )
   ```

4. **Monitor Subsystem Status**:
   ```python
   # Periodically check health
   status = tracker.get_subsystem_status()
   if status["mqtt"] == "failed":
       # Take action
       restart_mqtt_connection()
   ```

5. **Clear Old Errors**:
   ```python
   # After successful recovery
   tracker.clear_errors(category=ErrorCategory.MQTT_CONNECTION)
   ```

## Testing

See `tests/unit/test_error_tracker.py` (to be created) for comprehensive test coverage.

## Future Enhancements

- [ ] Persistence in SQLite for error history
- [ ] Prometheus metrics for error counts
- [ ] Email/Webhook notifications for critical errors
- [ ] Grafana dashboard for error visualization
- [ ] Automatic error aggregation (group similar errors)

## Related

- [MQTT Meta-Topics](./mqtt-topics.md#meta-topics)
- [WebUI API](./webui.md#api-endpoints)
- [Logging](./logging.md)
