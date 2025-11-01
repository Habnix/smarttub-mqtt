## Systematic Light Mode Discovery

This guide describes the systematic Light Mode Discovery used to determine which light modes and brightness combinations work reliably on a given SmartTub model. Different spa models support different capabilities; this process enumerates and verifies them.

### Parameters under test

- 18 light modes (OFF, PURPLE, ORANGE, RED, YELLOW, GREEN, AQUA, BLUE, WHITE, AMBER, HIGH_SPEED_COLOR_WHEEL, HIGH_SPEED_WHEEL, LOW_SPEED_WHEEL, FULL_DYNAMIC_RGB, AUTO_TIMER_EXTERIOR, PARTY, COLOR_WHEEL, ON)
- 5 brightness levels: 0%, 25%, 50%, 75%, 100%
- Strategy: test all brightness levels for each mode. OFF is tested only at 0%; other modes exclude 0% unless supported.

### Test flow

1. Per zone: ~90 checks (18 modes × ~5 brightness levels)
2. Delay between checks: 20s (give the SmartTub Cloud API time to apply changes)
3. Verification: call `get_lights()` after each change to confirm the mode/brightness was applied
4. Approximate duration: ~30 minutes per light zone

### Example sequence

```
OFF @ 0%
PURPLE @ 25%, 50%, 75%, 100%
ORANGE @ 25%, 50%, 75%, 100%
...
```

### Enabling discovery

Full light-mode discovery can be enabled via `/config/.env`:

```bash
CHECK_SMARTTUB=true
DISCOVERY_TEST_ALL_LIGHT_MODES=true
```

Then run normally (discovery runs on startup) or invoke discovery mode explicitly:

```bash
# Normal start (runs discovery on startup)
python -m src.cli.run

# Or run discovery-only with destructive probes
python -m src.cli.run --discover --perform-destructive-probes
```

Or run a one-off discovery:

```bash
DISCOVERY_TEST_ALL_LIGHT_MODES=true python -m src.cli.run --discover --perform-destructive-probes
```

### MQTT status topics

During discovery the bridge publishes progress and state under these topics:

- `smarttub-mqtt/{spa_id}/discovery/status` — values: `"testing"` | `"connected"` | `"error"`
- `smarttub-mqtt/{spa_id}/discovery/progress` — format: `"15/90"` (current test / total tests)
- `smarttub-mqtt/{spa_id}/discovery/detail` — e.g. `"Testing zone 1: RED @ 50%"`

### Results storage

Discovery results are stored in `/config/discovered_items.yaml`, for example:

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
        unsupported_modes:
          - PURPLE
          - RED
          - ORANGE
          - PARTY
        test_summary:
          total_tests: 90
          successful_tests: 12
          failed_tests: 78
```

### Special handling

- WHITE mode: RGB values are recorded per zone because they may vary across zones.
- Brightness support: for each supported mode we store the list of working brightness levels.

### Restoration

After the discovery run the bridge restores the original light state:

1. If the original state was known, restore that mode/brightness
2. Otherwise set lights to OFF as a safe fallback

### Safety

- Non-destructive: tests only temporarily change the light mode
- Automatic restoration after each run
- Timeouts protect against hung API calls

### Performance

- Total duration: ~60 minutes for 2 zones (180 checks × 20s)
- Per test: ~20s (15s delay + 2s verification + 3s API latency)
- Parallel execution is not supported — the Cloud API processes one change at a time

### Troubleshooting

If many tests fail:
1. Confirm the spa is online and not in sleep mode
2. Wait and retry — the Cloud API may be temporarily slow
3. Inspect `/tmp/smarttub-test-debug.log`

If discovery runs very long: this is expected for full light testing; monitor `discovery/progress` and optionally abort (Ctrl+C) and resume later.

If brightness is not supported for a mode, the YAML will show an empty `brightness_support` list for that mode — that indicates the mode accepts the command but brightness control is ineffective on that hardware.

### Integration

Other components can consult the discovered capabilities before issuing commands, for example:

```python
if mode not in discovered_capabilities["supported_modes"]:
    raise ValueError(f"Mode {mode} not supported by this spa")

if brightness not in discovered_capabilities["supported_modes"][mode]["brightness_support"]:
    raise ValueError(f"Brightness {brightness}% not supported for mode {mode}")
```

## See also

- [Discovery Tasks](tasks/discovery_tasks.md)
- [Discovery Spec](specs/discovery.md)
- [Configuration Guide](configuration.md)
