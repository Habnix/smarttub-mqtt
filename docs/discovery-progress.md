# Discovery Progress Tracking

**Status**: Implemented ✅ (T059)

## Overview

The Discovery Progress Tracking system provides real-time monitoring of discovery progress with detailed information about each phase and component.

## Architecture

### Components

- **DiscoveryProgressTracker** (`src/core/discovery_progress.py`): central progress-tracking class
- **MQTT Meta-Topic**: `{base_topic}/meta/discovery/progress` (JSON, retained, QoS 0)
- **WebUI API**: `/api/discovery/progress` (GET), `/api/discovery/progress/{spa_id}` (GET)
- **Integration**: ItemProber, MQTTBrokerClient, WebApp

### Discovery Phases

```python
class DiscoveryPhase(Enum):
    INITIALIZING = "initializing"
    CONNECTING = "connecting"
    FETCHING_SPAS = "fetching_spas"
    PROBING_SPA = "probing_spa"
    PROBING_PUMPS = "probing_pumps"
    PROBING_LIGHTS = "probing_lights"
    PROBING_HEATER = "probing_heater"
    PROBING_STATUS = "probing_status"
    WRITING_YAML = "writing_yaml"
    PUBLISHING_MQTT = "publishing_mqtt"
    COMPLETED = "completed"
    FAILED = "failed"
```

### Component Types

```python
class ComponentType(Enum):
    SPA = "spa"
    PUMP = "pump"
    LIGHT = "light"
    HEATER = "heater"
    STATUS = "status"
```

## Usage

### Tracking Discovery Progress

```python
from src.core.discovery_progress import DiscoveryProgressTracker, DiscoveryPhase, ComponentType

# Create tracker
tracker = DiscoveryProgressTracker()

# Start discovery session
tracker.start_discovery(total_spas=2)
tracker.set_overall_phase(DiscoveryPhase.FETCHING_SPAS)

# Start spa discovery
tracker.start_spa('spa123', 'Master Spa')
tracker.set_spa_component_count('spa123', 5)

# Track component
tracker.start_component('spa123', ComponentType.PUMP, 'pump_0', name='Jet Pump')
tracker.complete_component(
    'spa123', 
    'pump_0',
    example_info={'state': 'ON', 'speed': 2}
)

# Complete spa
tracker.complete_spa('spa123')

# Complete discovery
tracker.set_overall_phase(DiscoveryPhase.COMPLETED)
```

### Querying Progress

```python
# Get overall progress
progress = tracker.get_progress()
# Returns:
# {
#   "overall_phase": "probing_spa",
#   "started_at": "2025-10-30T12:00:00Z",
#   "completed_at": null,
#   "total_spas": 2,
#   "completed_spas": 0,
#   "overall_percent": 0,
#   "spas": {...}
# }

# Get spa-specific progress
spa_progress = tracker.get_spa_progress('spa123')
# Returns:
# {
#   "spa_id": "spa123",
#   "spa_name": "Master Spa",
#   "total_components": 5,
#   "completed_components": 2,
#   "progress_percent": 40,
#   "current_component": {...},
#   "components": [...]
# }
```

## MQTT Meta-Topic

### Topic Structure

```
smarttub-mqtt/meta/discovery/progress
```

### Payload Example

```json
{
  "timestamp": "2025-10-30T12:05:23Z",
  "overall_phase": "probing_spa",
  "started_at": "2025-10-30T12:00:00Z",
  "completed_at": null,
  "total_spas": 2,
  "completed_spas": 0,
  "overall_percent": 0,
  "spas": {
    "spa123": {
      "spa_id": "spa123",
      "spa_name": "Master Spa",
      "started_at": "2025-10-30T12:00:15Z",
      "completed_at": null,
      "total_components": 5,
      "completed_components": 2,
      "progress_percent": 40,
      "current_component": {
        "component_type": "pump",
        "component_id": "pump_1",
        "name": "Circulation Pump",
        "phase": "probing_pumps",
        "started_at": "2025-10-30T12:05:20Z",
        "completed_at": null,
        "error": null,
        "example_info": null
      },
      "components": [
        {
          "component_type": "status",
          "component_id": "status",
          "name": null,
          "phase": "completed",
          "started_at": "2025-10-30T12:00:20Z",
          "completed_at": "2025-10-30T12:00:25Z",
          "error": null,
          "example_info": {
            "water_temp": 38.5
          }
        },
        {
          "component_type": "pump",
          "component_id": "pump_0",
          "name": "Jet Pump",
          "phase": "completed",
          "started_at": "2025-10-30T12:00:30Z",
          "completed_at": "2025-10-30T12:00:35Z",
          "error": null,
          "example_info": {
            "state": "ON",
            "speed": 2
          }
        }
      ],
      "error": null
    }
  }
}
```

### Publishing

- **Automatically**: during discovery (real-time updates)
- **Retained**: Yes (last-known status remains visible)
- **QoS**: 0 (performance-optimized for frequent updates)

## WebUI API

### GET /api/discovery/progress

Returns overall discovery progress.

**Response:**
```json
{
  "timestamp": "2025-10-30T12:05:23Z",
  "progress": {
    "overall_phase": "probing_spa",
    "overall_percent": 25,
    "total_spas": 2,
    "completed_spas": 0,
    "spas": {...}
  },
  "available": true
}
```

### GET /api/discovery/progress/{spa_id}

Returns progress for a specific spa.

**Response:**
```json
{
  "timestamp": "2025-10-30T12:05:23Z",
  "spa_progress": {
    "spa_id": "spa123",
    "spa_name": "Master Spa",
    "progress_percent": 40,
    "current_component": {...},
    "components": [...]
  },
  "available": true
}
```

## Integration

### ItemProber

```python
from src.core.item_prober import ItemProber
from src.core.discovery_progress import DiscoveryProgressTracker

tracker = DiscoveryProgressTracker()
prober = ItemProber(config, smarttub_client, topic_mapper, progress_tracker=tracker)

# Discovery automatically tracks progress
results = await prober.probe_all()
```

### MQTTBrokerClient

```python
from src.mqtt.broker_client import MQTTBrokerClient

broker = MQTTBrokerClient(config)

# Publish progress updates
progress_data = tracker.get_progress()
broker.publish_discovery_progress(progress_data)
```

### WebUI

```python
from src.web.app import create_app

app = create_app(config, state_manager, progress_tracker=tracker)

# API endpoints automatically available:
# - GET /api/discovery/progress
# - GET /api/discovery/progress/{spa_id}
```

## Progress Calculation

### Overall Progress

```python
overall_percent = (completed_spas / total_spas) * 100
```

### Spa Progress

```python
spa_percent = (completed_components / total_components) * 100
```

## Thread Safety

All DiscoveryProgressTracker operations are thread-safe via internal locking mechanisms.

```python
# Safe from multiple threads
tracker.start_component(...)  # Thread-safe
tracker.complete_component(...)  # Thread-safe
tracker.get_progress()  # Thread-safe
```

## Example Data

### Component Example Info

Each component can include `example_info` with example data:

- **Status**: `{"water_temp": 38.5, "heater_state": "ON"}`
- **Pump**: `{"state": "ON", "speed": 2, "type": "CIRCULATION"}`
- **Light**: `{"state": "ON", "mode": "WHITE", "brightness": 75}`
- **Heater**: `{"target_temp": 40.0, "current_temp": 38.5}`

These example fields help configuration and give immediate insight into discovered values.

## Best Practices

1. **Start Discovery Early**:
   ```python
   tracker.start_discovery(total_spas=len(spas))
   ```

2. **Set Component Counts**:
   ```python
   # Estimate component count for accurate progress
   tracker.set_spa_component_count(spa_id, estimated_components)
   ```

3. **Provide Example Info**:
   ```python
   # Include useful example data
   tracker.complete_component(
       spa_id, 
       component_id,
       example_info={"water_temp": 38.5, "state": "READY"}
   )
   ```

4. **Handle Errors Gracefully**:
   ```python
   try:
       # Probe component
       data = await probe_component()
       tracker.complete_component(spa_id, component_id, example_info=data)
   except Exception as e:
       tracker.complete_component(spa_id, component_id, error=str(e))
   ```

5. **Publish Progress Updates**:
   ```python
   # Publish to MQTT regularly during discovery
   progress = tracker.get_progress()
   broker.publish_discovery_progress(progress)
   ```

### Monitoring Discovery

### Via MQTT

```bash
# Subscribe to progress updates
mosquitto_sub -t 'smarttub-mqtt/meta/discovery/progress' -v
```

### Via WebUI API

```bash
# Get overall progress
curl http://localhost:8080/api/discovery/progress

# Get spa-specific progress
curl http://localhost:8080/api/discovery/progress/spa123
```

### Via WebUI Dashboard

Accessing the WebUI at `http://localhost:8080` will display discovery progress automatically (if implemented).

## Testing

See the end-to-end test above for full test coverage.

## Future Enhancements

- [ ] WebSocket-based real-time updates for the WebUI
- [ ] Progress bar component in the UI
- [ ] Persist historical discovery runs
- [ ] Progress notifications (email/webhook)
- [ ] Estimated time remaining (ETA)

## Related

- [Error Tracking](./error-tracking.md)
- [MQTT Meta-Topics](./mqtt-topics.md#meta-topics)
- [Discovery Process](./discovery.md)
- [WebUI API](./webui.md#api-endpoints)
