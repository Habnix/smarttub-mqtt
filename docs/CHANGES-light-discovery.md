# Systematic Light Mode Discovery - Implementation Overview

**Date**: 2025-01-23  
**Feature**: Exhaustive Light Mode & Brightness Testing  
````markdown
# Systematic Light Mode Discovery - Implementation Overview

**Date**: 2025-01-23  
**Feature**: Exhaustive Light Mode & Brightness Testing  
**Status**: Implemented ✅

## Overview

The systematic Light Mode Discovery has been integrated into the existing `ItemProber`. It tests all available light modes and brightness levels to determine which combinations work for a specific spa.

## Implemented files

### 1. `/var/python/smarttub-mqtt/src/core/item_prober.py`

**New class constants:**
- `ALL_LIGHT_MODES`: list of the 18 known light modes
- `BRIGHTNESS_LEVELS`: [0, 25, 50, 75, 100]
- `LIGHT_TEST_DELAY_SECONDS`: 20 seconds wait time between tests

**Extended logic inside `_probe_spa()`:**
- Checks the `config.discovery_test_all_light_modes` flag
- If enabled: calls `_test_all_light_modes()`
- Publishes MQTT status during testing: `"testing"` → `"connected"`
- Falls back to the original quick-test when the flag is not set

**New method: `_test_all_light_modes(spa, light_obj, spa_id)`**
- Performs systematic tests for a light zone
- Tests all mode × brightness combinations
- OFF mode only with brightness = 0
- Other modes: brightness 25%, 50%, 75%, 100% (skip 0%)
- Publishes progress to MQTT:
  - `{base_topic}/{spa_id}/discovery/progress`: "15/90"
  - `{base_topic}/{spa_id}/discovery/detail`: "Testing zone 1: RED @ 50%"
- Captures RGB values for WHITE mode
- Restores original state after tests
- Returns a dictionary with results, e.g.:
  ```python
  {
    "id": "zone_1",
    "zone": 1,
    "zone_type": "INTERIOR",
    "supported_modes": {
      "WHITE": {
        "brightness_support": [0, 25, 50, 75, 100],
        "rgb": {"red": 170, "green": 170, "blue": 170, "white": 0}
      }
    },
    "unsupported_modes": ["PURPLE", "RED", ...],
    "test_summary": {
      "total_tests": 90,
      "successful_tests": 12,
      "failed_tests": 78
    }
  }
  ```

**New method: `_test_light_mode(spa, light_obj, mode_name, brightness, zone, spa_id)`**
- Tests a specific mode/brightness combination
- Verifies the mode exists in `smarttub.SpaLight.LightMode` enum
- Calls `light_obj.set_mode(mode_name, brightness)`
- Waits 2 seconds for API propagation
- Verifies via `spa.get_lights()`
- Compares returned mode and brightness
- Returns `True` on success, `False` on failure
- Detailed debug logging for every test

### 2. `/var/python/smarttub-mqtt/src/core/config_loader.py`

**New AppConfig attribute:**
```python
discovery_test_all_light_modes: bool = False  # Default: False
```

**Environment variable support:**
```python
if "DISCOVERY_TEST_ALL_LIGHT_MODES" in env:
    config.discovery_test_all_light_modes = _coerce_bool(
        env.get("DISCOVERY_TEST_ALL_LIGHT_MODES"), 
        "DISCOVERY_TEST_ALL_LIGHT_MODES"
    )
```

### 3. `/var/python/smarttub-mqtt/docs/discovery-light-modes.md`

Comprehensive documentation including:
- How it works and the testing strategy
- Activation instructions (2 methods)
- MQTT status topics
- YAML output format with examples
- WHITE mode RGB capture
- Brightness support lists
- Restore logic
- Security and performance notes
- Troubleshooting

### 4. `/var/python/smarttub-mqtt/README.md`

Updated feature list:
```markdown
### 📊 Discovery & Capability Detection
- Automatic spa detection on startup
- Capability probing for pumps, lights, heater
- **Systematic Light Mode Testing**: Tests all 18 light modes × 5 brightness levels
- Progress tracking with real-time updates via MQTT
- YAML export of discovered configuration
- See [Discovery Light Modes Guide](docs/discovery-light-modes.md)
```

### 5. `/var/python/smarttub-mqtt/docs/configuration.md`

New section under "Discovery & Capability Configuration":
```markdown
**Light Mode Discovery:**

The `DISCOVERY_TEST_ALL_LIGHT_MODES` option enables systematic testing of all available light modes:

- Tests **all 18 light modes** × **5 brightness levels** (0%, 25%, 50%, 75%, 100%)
- Duration: ~30 minutes per light zone
- Output: YAML file listing all functional mode/brightness combinations
- See [Discovery Light Modes Guide](discovery-light-modes.md) for details
```

### 6. `/var/python/smarttub-mqtt/config/.env.example`

New environment variable with documentation:
```bash
# Discovery Settings
# Enables discovery at program startup (checks available spa features)
CHECK_SMARTTUB=true

# Systematic Light Mode Testing (optional, time-consuming!)
# Tests all 18 light modes × 5 brightness levels (~30 min per zone)
# Output is stored in /config/discovered_items.yaml
# See docs/discovery-light-modes.md for details
DISCOVERY_TEST_ALL_LIGHT_MODES=false
```

## Deleted files

The following redundant files were removed because the functionality was integrated into `ItemProber`:

- `/var/python/smarttub-mqtt/src/discovery/capability_detector.py` (DELETED)
- `/var/python/smarttub-mqtt/src/discovery/discovery_store.py` (DELETED)
- `/var/python/smarttub-mqtt/src/discovery/__init__.py` (DELETED)

## Integration with existing code

The implementation integrates into the existing discovery flow:

1. **Discovery trigger**: `ItemProber` is invoked at startup (via `CHECK_SMARTTUB=true`)
2. **Destructive probes**: The `--perform-destructive-probes` flag enables destructive tests
3. **YAML storage**: Uses the existing `_write_yaml()` method
4. **MQTT publishing**: Uses the existing `topic_mapper` and `mqtt_client`
5. **Error tracking**: Uses the existing `error_tracker` integration

## Usage

### Step 1: Enable

In `/config/.env`:
```bash
CHECK_SMARTTUB=true
DISCOVERY_TEST_ALL_LIGHT_MODES=true
```

### Step 2: Start discovery

```bash
# Method A: Discovery on normal start
python -m src.cli.run

# Method B: Discovery-only mode
python -m src.cli.run --discover --perform-destructive-probes
```

### Step 3: Monitoring

Monitor MQTT topics:
```bash
# Status
mosquitto_sub -h 192.168.178.164 -t 'smarttub-mqtt/100946961/discovery/status'

# Progress
mosquitto_sub -h 192.168.178.164 -t 'smarttub-mqtt/100946961/discovery/progress'

# Details
mosquitto_sub -h 192.168.178.164 -t 'smarttub-mqtt/100946961/discovery/detail'
```

### Step 4: Inspect results

```bash
# Show YAML output
cat /config/discovered_items.yaml

# Or via CLI
python -m src.cli.run --show-discovery
```

## Test statistics

**Per light zone:**
- Modes: 18
- Brightness levels per mode: ~5 (OFF only 0%, others 25-100%)
- Tests per zone: ~90
- Delay per test: 20 seconds
- **Total duration per zone: ~30 minutes**

**For a spa with 2 zones:**
- Total tests: 180
- **Total duration: ~60 minutes**

## Expected YAML output

After successful discovery `/config/discovered_items.yaml` will include:

```yaml
discovered_items:
  100946961:
    spa_id: 100946961
    discovered_at: "2025-01-23T10:30:00Z"
    lights:
      - id: zone_1
        zone: 1
        zone_type: INTERIOR
        supported_modes:
          WHITE:
            brightness_support: [0, 25, 50, 75, 100]
            rgb:
              red: 170
              green: 170
              blue: 170
              white: 0
          HIGH_SPEED_COLOR_WHEEL:
            brightness_support: [25, 50, 75, 100]
            rgb: null
          LOW_SPEED_WHEEL:
            brightness_support: [25, 50, 75, 100]
            rgb: null
        unsupported_modes:
          - PURPLE
          - ORANGE
          - RED
          - YELLOW
          - GREEN
          - AQUA
          - BLUE
          - AMBER
          - FULL_DYNAMIC_RGB
          - AUTO_TIMER_EXTERIOR
          - PARTY
          - COLOR_WHEEL
          - ON
        test_summary:
          total_tests: 90
          successful_tests: 15
          failed_tests: 75
```

## Next steps

1. **Test with a real spa**: Run discovery against your spa
2. **Validate results**: Inspect the `discovered_items.yaml`
3. **Command validation**: Use results to validate light commands
4. **WebUI integration**: Display only supported modes in the WebUI
5. **Home Assistant**: Use discovery data for HA integration

## Known limitations

1. **Duration**: Tests are time-consuming (30+ minutes per zone)
   - Reason: 20 second delay needed for cloud API propagation
   - Mitigation: Parallel testing is not possible (cloud API limitation)

2. **Spa must be online**: Tests will fail if the spa is offline/asleep
   - Mitigation: Ensure the spa is active and connected

3. **Brightness verification is imprecise**: Some spas accept brightness values but do not actually change visible brightness
   - Mitigation: Comparing with `get_lights()` catches most cases

## Technical details

### Verification logic

```python
# After set_mode(mode_name, brightness):
await asyncio.sleep(2)  # Wait for API propagation

lights = await spa.get_lights()
for l in lights['lights']:
    if l.zone == zone:
        current_mode = l.mode.name
        current_intensity = l.intensity
        
        if mode_name == "OFF":
            success = (current_mode == "OFF")
        else:
            success = (current_mode == mode_name and 
                      current_intensity == brightness)
```

### RGB capture

```python
# Only for WHITE mode:
if mode_name == "WHITE" and test_success:
    mode_results["rgb"] = {
        "red": l.red,
        "green": l.green,
        "blue": l.blue,
        "white": l.white,
    }
```

### Restore logic

```python
# Capture original state
orig_mode = getattr(light_obj, 'mode', None)
orig_intensity = getattr(light_obj, 'intensity', None)

# ... run all tests ...

# Restore
if orig_mode:
    await light_obj.set_mode(orig_mode.name, orig_intensity)
else:
    await light_obj.set_mode("OFF", 0)  # Safe default
```

## Maintenance

### Log monitoring

```bash
tail -f /tmp/smarttub-test-debug.log | grep -E "zone|mode test|Testing zone"
```

### MQTT debugging

```bash
# Monitor all discovery topics
mosquitto_sub -v -h 192.168.178.164 -t 'smarttub-mqtt/+/discovery/#'
```

### Performance tuning

If needed, `LIGHT_TEST_DELAY_SECONDS` can be adjusted:

```python
# In item_prober.py
LIGHT_TEST_DELAY_SECONDS = 15  # Faster but less reliable
# or
LIGHT_TEST_DELAY_SECONDS = 30  # Slower but more reliable
```

## Changelog

- **2025-01-23**: Initial implementation
  - Systematic light mode testing in ItemProber
  - DISCOVERY_TEST_ALL_LIGHT_MODES config option
  - MQTT progress topics
  - Documentation created

````
