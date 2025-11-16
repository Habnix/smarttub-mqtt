# Background Discovery - Light Mode Detection

## Overview

SmartTub-MQTT v0.3.0 introduces **Background Discovery** - an automated system to detect which light modes your whirlpool actually supports. Instead of guessing or manual testing, the system can automatically test all available modes and remember which ones work.

## Features

- 🔍 **Automatic Mode Testing**: Tests all 18 known light modes automatically
- ⚡ **Three Discovery Modes**: Choose between YAML-only (instant), Quick (~5 min), or Full (~20 min)
- 🌐 **WebUI Control**: User-friendly web interface for starting/stopping discovery
- 📡 **MQTT Control**: Start/stop discovery via MQTT messages
- 💾 **Persistent Storage**: Results saved to `/config/discovered_items.yaml`
- 📊 **Live Progress**: Real-time progress updates with percentage completion
- 🔄 **YAML Fallback**: Automatically publishes saved modes at startup

## Discovery Modes

### YAML Only (Instant)
- **Duration**: Instant
- **What it does**: Loads and publishes modes from existing `discovered_items.yaml`
- **Use case**: You already ran discovery and just want to reload the results

### Quick (~5 minutes)
- **Duration**: ~5 minutes
- **Modes tested**: 4 common modes (OFF, ON, PURPLE, WHITE)
- **Wait time**: 8 seconds per mode
- **Use case**: Quick check of basic functionality

### Full (~20 minutes)
- **Duration**: ~20 minutes
- **Modes tested**: All 18 known modes
- **Wait time**: 20 seconds per mode
- **Use case**: Complete discovery of all supported modes

## Usage

### Via WebUI

1. **Access Discovery Page**
   - Navigate to `http://<your-ip>:8080/discovery`
   - Or click "Discovery" in the navigation bar

2. **Select Mode**
   - Click on one of the mode cards (YAML Only, Quick, or Full)

3. **Start Discovery**
   - Click "Start Discovery" button
   - Watch the live progress bar

4. **View Results**
   - After completion, results appear automatically
   - Shows detected modes for each light

### Via MQTT

**Control Topic**: `smarttub-mqtt/discovery/control`

**Start Discovery**:
```json
{
  "action": "start",
  "mode": "quick"
}
```

Modes: `"full"`, `"quick"`, or `"yaml_only"`

**Stop Discovery**:
```json
{
  "action": "stop"
}
```

**Status Topic**: `smarttub-mqtt/discovery/status`

Real-time status updates (not retained):
```json
{
  "status": "running",
  "mode": "quick",
  "started_at": "2025-11-09T15:00:00Z",
  "progress": {
    "percentage": 45.5,
    "current_spa": "spa-001",
    "current_light": "zone_1",
    "modes_tested": 5,
    "modes_total": 18
  }
}
```

**Result Topic**: `smarttub-mqtt/discovery/result`

Final results (retained):
```json
{
  "completed_at": "2025-11-09T15:20:00Z",
  "yaml_path": "/config/discovered_items.yaml",
  "total_lights": 2,
  "total_modes_detected": 8,
  "spas": {
    "spa-001": {
      "lights": [
        {
          "id": "zone_1",
          "detected_modes": ["OFF", "ON", "PURPLE", "WHITE"]
        }
      ]
    }
  }
}
```

### Automatic Startup Discovery

Set the `DISCOVERY_MODE` environment variable to run discovery automatically at startup:

```bash
# No automatic discovery (default)
DISCOVERY_MODE=off

# Quick discovery at startup
DISCOVERY_MODE=startup_quick

# Full discovery at startup
DISCOVERY_MODE=startup_full

# YAML-only at startup
DISCOVERY_MODE=startup_yaml
```

**Docker Compose Example**:
```yaml
services:
  smarttub-mqtt:
    image: willnix/smarttub-mqtt:latest
    environment:
      - DISCOVERY_MODE=startup_quick
    # ... other settings
```

## Output Format

Discovery results are saved to `/config/discovered_items.yaml`:

```yaml
discovered_items:
  spa-001:
    lights:
      - id: zone_1
        zone: 1
        detected_modes:
          - OFF
          - ON
          - PURPLE
          - WHITE
          - HIGH_SPEED_COLOR_WHEEL
      - id: zone_2
        zone: 2
        detected_modes:
          - OFF
          - ON
```

## MQTT Topics

The detected modes are published to MQTT at startup and after discovery:

**Topic**: `smarttub-mqtt/{spa_id}/light/{light_id}/meta/detected_modes`

**Payload**: Comma-separated list of modes
```
OFF,ON,PURPLE,WHITE,HIGH_SPEED_COLOR_WHEEL
```

**Properties**:
- QoS: 1
- Retained: Yes

## How It Works

1. **Login**: Connects to SmartTub API
2. **Enumerate**: Gets all spas and their lights
3. **Test Modes** (if enabled):
   - For each light
   - For each mode to test
   - Sets the mode
   - Waits configured time
   - Marks as detected if successful
4. **Save Results**: Writes to YAML file
5. **Publish**: Updates MQTT topics

## Progress Tracking

During discovery, the system tracks:
- Current spa being tested
- Current light being tested
- Number of lights tested / total
- Number of modes tested / total
- Percentage completion (0-100%)

Progress is calculated as:
```
percentage = (modes_tested / modes_total) * 100
```

## Error Handling

- **Login Failures**: Discovery fails with error message
- **API Errors**: Logged but discovery continues
- **Mode Set Failures**: Mode marked as not supported
- **Timeout**: Can be stopped gracefully at any time

## Graceful Shutdown

Discovery can be stopped at any time:
- Via WebUI "Stop Discovery" button
- Via MQTT stop command
- Via SIGTERM/SIGINT signal

The system will:
1. Set stop flag
2. Wait for current mode test to complete (max 10 seconds)
3. Save partial results
4. Update state to idle

## Troubleshooting

### Discovery Never Completes

**Symptom**: Progress bar stuck at a percentage

**Possible Causes**:
- Light not responding to API commands
- Network issues between SmartTub and spa
- Mode not supported (but API doesn't error)

**Solution**:
- Stop discovery via WebUI or MQTT
- Check SmartTub app to see if light is responsive
- Try Quick mode instead of Full mode

### No Modes Detected

**Symptom**: All detected_modes arrays are empty

**Possible Causes**:
- Lights don't support the tested modes
- Light module hardware issue
- Firmware issue

**Solution**:
- Verify lights work in SmartTub app
- Try manually setting modes in SmartTub app
- Contact SmartTub support if lights don't work

### YAML Not Found at Startup

**Symptom**: Warning in logs: "YAML file not found"

**This is normal** on first startup. Run discovery once to create the file.

### Discovery Starts Automatically

**Symptom**: Discovery runs on every startup

**Cause**: `DISCOVERY_MODE` environment variable is set to `startup_quick` or `startup_full`

**Solution**:
- Set `DISCOVERY_MODE=off` (or remove the variable)
- Restart container

## Performance Considerations

### Full Discovery (~20 minutes)
- Tests 18 modes per light
- 20 seconds per mode
- For 2 lights: ~18 minutes total

### Quick Discovery (~5 minutes)
- Tests 4 modes per light
- 8 seconds per mode
- For 2 lights: ~4 minutes total

### YAML Only (Instant)
- No API calls
- Just loads and publishes
- < 1 second

## Best Practices

1. **Run Full Discovery Once**: Get complete mode list initially
2. **Use YAML Fallback**: After that, rely on saved results
3. **Manual Updates**: Only re-run if you change light hardware
4. **Quick Mode for Testing**: Use Quick mode if you just want to verify lights work
5. **Avoid Frequent Full Discovery**: It's slow and unnecessary

## API Reference

### REST API Endpoints

```
GET  /api/discovery/status   - Get current status
POST /api/discovery/start    - Start discovery
POST /api/discovery/stop     - Stop discovery
GET  /api/discovery/results  - Get results
POST /api/discovery/reset    - Reset state
GET  /discovery              - WebUI page
```

### Python API

```python
from src.core.discovery_coordinator import DiscoveryCoordinator

# Initialize
coordinator = DiscoveryCoordinator(
    smarttub_client=client,
    config=config
)

# Start discovery
await coordinator.start_discovery(mode="quick")

# Get status
status = await coordinator.get_status()

# Stop discovery
await coordinator.stop_discovery()

# Get results
results = await coordinator.get_results()
```

## Version History

- **v0.3.0**: Initial release of Background Discovery
  - Three discovery modes (Full, Quick, YAML Only)
  - WebUI control
  - MQTT control
  - YAML fallback publishing
  - Startup automation

## See Also

- [Main README](../README.md)
- [MQTT Topics](mqtt-topics.md)
- [WebUI Guide](webui.md)
