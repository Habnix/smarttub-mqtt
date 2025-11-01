# Automation Migration Guide

## Overview

This guide helps migrate existing home automation integrations (OpenHAB, Home Assistant, Node-RED) to SmartTub-MQTT v1.0.

## Topic Structure Changes

### No breaking changes! ✅

Version 1.0 preserves backwards compatibility:

- **Legacy Topics** (without `spa_id`) will continue to be published
- **New Topics** (with `spa_id`) are now available
- Both topic structures exist in parallel

### Recommended migration

**Alt (Legacy, funktioniert weiter):**
```
smarttub-mqtt/heater/target_temperature
smarttub-mqtt/pumps/CP/state
```

**New (multi-spa capable, recommended):**
```
smarttub-mqtt/{spa_id}/heater/target_temperature
smarttub-mqtt/{spa_id}/pumps/CP/state
```

## OpenHAB Migration

### Single Spa Setup (no change required)

**Old items (continue to work):**

```java
// items/smarttub.items
Number SpaTargetTemp "Target temperature [%.1f °C]" 
    { mqtt=">[broker:smarttub-mqtt/heater/target_temperature_writetopic:command:*:default],
            <[broker:smarttub-mqtt/heater/target_temperature:state:default]" }

Switch SpaPump "Pumpe" 
    { mqtt=">[broker:smarttub-mqtt/pumps/CP/state_writetopic:command:MAP(pump.map)],
            <[broker:smarttub-mqtt/pumps/CP/state:state:MAP(pump.map)]" }
```

**Empfohlen (mit spa_id):**

```java
// items/smarttub.items
String spaId = "spa_abc123"  // Your Spa ID

Number SpaTargetTemp "Target temperature [%.1f °C]" 
    { mqtt=">[broker:smarttub-mqtt/%s/heater/target_temperature_writetopic:command:*:default],
            <[broker:smarttub-mqtt/%s/heater/target_temperature:state:default]",
      spaId="%s" }

Switch SpaPump "Pump" 
    { mqtt=">[broker:smarttub-mqtt/%s/pumps/CP/state_writetopic:command:MAP(pump.map)],
            <[broker:smarttub-mqtt/%s/pumps/CP/state:state:MAP(pump.map)]",
      spaId="%s" }
```

### Multi-Spa Setup (spa_id required)

**For multiple spas:**

```java
// items/spa1.items
String spa1Id = "spa_abc123"

Group gSpa1 "Spa 1 [Master Spa]"

Number Spa1TargetTemp "Spa 1 Target temperature [%.1f °C]" (gSpa1)
    { mqtt=">[broker:smarttub-mqtt/spa_abc123/heater/target_temperature_writetopic:command:*:default],
            <[broker:smarttub-mqtt/spa_abc123/heater/target_temperature:state:default]" }

// items/spa2.items
String spa2Id = "spa_xyz789"

Group gSpa2 "Spa 2 [Guest Spa]"

Number Spa2TargetTemp "Spa 2 Target temperature [%.1f °C]" (gSpa2)
    { mqtt=">[broker:smarttub-mqtt/spa_xyz789/heater/target_temperature_writetopic:command:*:default],
            <[broker:smarttub-mqtt/spa_xyz789/heater/target_temperature:state:default]" }
```

### Error Monitoring (New)

```java
// items/smarttub_monitoring.items
String SpaErrors "Spa Errors" 
    { mqtt="<[broker:smarttub-mqtt/meta/errors:state:JSONPATH($.error_summary)]" }

Number SpaErrorCount "Error Count [%d]" 
    { mqtt="<[broker:smarttub-mqtt/meta/errors:state:JSONPATH($.error_summary.total_errors)]" }

String SpaSubsystemStatus "Subsystem Status" 
    { mqtt="<[broker:smarttub-mqtt/meta/errors:state:JSONPATH($.subsystem_status)]" }
```

### Discovery Progress (New)

```java
// items/smarttub_discovery.items
Number SpaDiscoveryProgress "Discovery Progress [%d %%]" 
    { mqtt="<[broker:smarttub-mqtt/meta/discovery:state:JSONPATH($.overall_percent)]" }

String SpaDiscoveryPhase "Discovery Phase" 
    { mqtt="<[broker:smarttub-mqtt/meta/discovery:state:JSONPATH($.overall_phase)]" }
```

## Home Assistant Migration

### Single Spa (no change required)

**Old config (continues to work):**

```yaml
# configuration.yaml
mqtt:
  climate:
    - name: "Spa Heater"
      current_temperature_topic: "smarttub-mqtt/heater/current_temperature"
      temperature_state_topic: "smarttub-mqtt/heater/target_temperature"
      temperature_command_topic: "smarttub-mqtt/heater/target_temperature_writetopic"
      min_temp: 26
      max_temp: 40
      temp_step: 0.5
      modes: ["heat", "off"]
  
  switch:
    - name: "Spa Pump"
      state_topic: "smarttub-mqtt/pumps/CP/state"
      command_topic: "smarttub-mqtt/pumps/CP/state_writetopic"
      payload_on: "HIGH"
      payload_off: "OFF"
```

**Recommended (with spa_id):**

```yaml
# configuration.yaml
mqtt:
  climate:
    - name: "Spa Heater"
      current_temperature_topic: "smarttub-mqtt/spa_abc123/heater/current_temperature"
      temperature_state_topic: "smarttub-mqtt/spa_abc123/heater/target_temperature"
      temperature_command_topic: "smarttub-mqtt/spa_abc123/heater/target_temperature_writetopic"
      min_temp: 26
      max_temp: 40
      temp_step: 0.5
      modes: ["heat", "off"]
  
  switch:
    - name: "Spa Pump"
      state_topic: "smarttub-mqtt/spa_abc123/pumps/CP/state"
      command_topic: "smarttub-mqtt/spa_abc123/pumps/CP/state_writetopic"
      payload_on: "HIGH"
      payload_off: "OFF"
```

### Multi-Spa Setup

```yaml
# configuration.yaml
mqtt:
  # Spa 1
  climate:
    - name: "Master Spa Heater"
      unique_id: "spa_abc123_heater"
      current_temperature_topic: "smarttub-mqtt/spa_abc123/heater/current_temperature"
      temperature_state_topic: "smarttub-mqtt/spa_abc123/heater/target_temperature"
      temperature_command_topic: "smarttub-mqtt/spa_abc123/heater/target_temperature_writetopic"
      min_temp: 26
      max_temp: 40
  
  # Spa 2
  climate:
    - name: "Guest Spa Heater"
      unique_id: "spa_xyz789_heater"
      current_temperature_topic: "smarttub-mqtt/spa_xyz789/heater/current_temperature"
      temperature_state_topic: "smarttub-mqtt/spa_xyz789/heater/target_temperature"
      temperature_command_topic: "smarttub-mqtt/spa_xyz789/heater/target_temperature_writetopic"
      min_temp: 26
      max_temp: 40
```

### Error Monitoring (Neu)

```yaml
# configuration.yaml
mqtt:
  sensor:
    - name: "SmartTub Error Count"
      state_topic: "smarttub-mqtt/meta/errors"
      value_template: "{{ value_json.error_summary.total_errors }}"
      json_attributes_topic: "smarttub-mqtt/meta/errors"
      json_attributes_template: "{{ value_json | tojson }}"
      icon: "mdi:alert-circle"
    
    - name: "SmartTub MQTT Status"
      state_topic: "smarttub-mqtt/meta/errors"
      value_template: "{{ value_json.subsystem_status.mqtt }}"
      icon: "mdi:server-network"
    
    - name: "SmartTub Discovery Status"
      state_topic: "smarttub-mqtt/meta/errors"
      value_template: "{{ value_json.subsystem_status.discovery }}"
      icon: "mdi:radar"
```

### Discovery Progress (Neu)

```yaml
# configuration.yaml
mqtt:
  sensor:
    - name: "SmartTub Discovery Progress"
      state_topic: "smarttub-mqtt/meta/discovery"
      value_template: "{{ value_json.overall_percent }}"
      unit_of_measurement: "%"
      icon: "mdi:progress-check"
    
    - name: "SmartTub Discovery Phase"
      state_topic: "smarttub-mqtt/meta/discovery"
      value_template: "{{ value_json.overall_phase }}"
      icon: "mdi:progress-clock"
```

### Automation Examples (New)

```yaml
# automations.yaml

# Alert on critical errors
- alias: "SmartTub Critical Error Alert"
  trigger:
    - platform: mqtt
      topic: "smarttub-mqtt/meta/errors"
  condition:
    - condition: template
      value_template: >
        {{ trigger.payload_json.subsystem_status.mqtt == 'failed' or
           trigger.payload_json.subsystem_status.smarttub_api == 'failed' }}
  action:
    - service: notify.mobile_app
      data:
        title: "SmartTub Critical Error"
        message: "SmartTub system has critical errors"

# Notify when discovery completes
- alias: "SmartTub Discovery Complete"
  trigger:
    - platform: mqtt
      topic: "smarttub-mqtt/meta/discovery"
  condition:
    - condition: template
      value_template: "{{ trigger.payload_json.overall_percent == 100 }}"
  action:
    - service: notify.mobile_app
      data:
        title: "SmartTub Discovery Complete"
        message: "Spa discovery finished successfully"
```

## Node-RED Migration

### Basic Flow (Legacy Topics)

**Works without changes:**

```json
[
  {
    "id": "mqtt-in",
    "type": "mqtt in",
    "topic": "smarttub-mqtt/heater/target_temperature",
    "qos": "1"
  },
  {
    "id": "mqtt-out",
    "type": "mqtt out",
    "topic": "smarttub-mqtt/heater/target_temperature_writetopic",
    "qos": "1"
  }
]
```

### Enhanced Flow (mit spa_id)

```json
[
  {
    "id": "mqtt-in-temp",
    "type": "mqtt in",
    "topic": "smarttub-mqtt/spa_abc123/heater/target_temperature",
    "qos": "1"
  },
  {
    "id": "mqtt-in-errors",
    "type": "mqtt in",
    "topic": "smarttub-mqtt/meta/errors",
    "qos": "1"
  },
  {
    "id": "parse-errors",
    "type": "function",
    "func": "msg.payload = JSON.parse(msg.payload);\nreturn msg;"
  }
]
```

### Error Monitoring Flow (Neu)

```json
[
  {
    "id": "error-monitor",
    "type": "mqtt in",
    "topic": "smarttub-mqtt/meta/errors",
    "qos": "1",
    "wires": [["parse-json"]]
  },
  {
    "id": "parse-json",
    "type": "json"
  },
  {
    "id": "check-critical",
    "type": "switch",
    "property": "payload.subsystem_status.mqtt",
    "rules": [
      {"t": "eq", "v": "failed"}
    ],
    "wires": [["alert"]]
  },
  {
    "id": "alert",
    "type": "debug",
    "name": "Critical Error Alert"
  }
]
```

### Migration Checklist

### Preparation

- [ ] Backup existing automation configuration
- [ ] Determine Spa ID(s) (WebUI or MQTT: `smarttub-mqtt/+/status/online`)
- [ ] Document legacy topics

### OpenHAB

- [ ] Update items to include `spa_id`
- [ ] Add error monitoring items
- [ ] Add discovery progress items
- [ ] Update sitemaps (if needed)
- [ ] Test rules

### Home Assistant

- [ ] Update MQTT entities to include `spa_id`
- [ ] Add error sensors
- [ ] Add discovery progress sensors
- [ ] Create automations for error alerts
- [ ] Verify configuration: `hass --script check_config`

### Node-RED

- [ ] Update MQTT topics to include `spa_id`
- [ ] Add error monitoring flow
- [ ] Add discovery progress flow
- [ ] Deploy and test flows

### Testing

- [ ] Subscribe to topics: `mosquitto_sub -t 'smarttub-mqtt/#' -v`
- [ ] Test commands (heater, pumps, lights)
- [ ] Verify error monitoring
- [ ] Observe discovery progress
- [ ] Test multi-spa separation (if applicable)

## Rollback

If issues occur:

### Continue using legacy topics

No changes required - legacy topics continue to work!

### OpenHAB Rollback

```bash
# Restore backup
cp items/smarttub.items.backup items/smarttub.items
sudo systemctl restart openhab
```

### Home Assistant Rollback

```bash
# Restore backup
cp configuration.yaml.backup configuration.yaml
hass --script check_config
sudo systemctl restart home-assistant
```

### Troubleshooting

### Topics not visible

```bash
# Check all topics
mosquitto_sub -h broker -t 'smarttub-mqtt/#' -v

# Check spa_id
mosquitto_sub -h broker -t 'smarttub-mqtt/+/status/online' -v
```

### Commands funktionieren nicht

**Check Write Topics:**
```bash
# Publish test command
mosquitto_pub -h broker -t 'smarttub-mqtt/spa_abc123/heater/target_temperature_writetopic' -m '40'

# Check errors
mosquitto_sub -h broker -t 'smarttub-mqtt/meta/errors' -v
```

### Determine Spa ID

**Option 1: WebUI**
- Open http://localhost:8080
- Spa ID is shown in the dashboard

**Option 2: MQTT**
```bash
mosquitto_sub -t 'smarttub-mqtt/+/status/online' -v
# Output: smarttub-mqtt/spa_abc123/status/online true
```

**Option 3: Logs**
```bash
docker logs smarttub-mqtt | grep "Spa ID"
```

## Support

For questions or issues:

- **GitHub Issues**: [Report Issue](https://github.com/your-org/smarttub-mqtt/issues)
- **Documentation**: [docs/](../)
- **Migration Tool**: `python tools/migrate.py --help`

## Related

-- [Migration Guide](./migration.md) - Config migration
-- [Configuration Guide](./configuration.md) - All parameters
-- [Error Tracking](./error-tracking.md) - Error monitoring
-- [Discovery Progress](./discovery-progress.md) - Discovery tracking
