# Logging Configuration

## Overview

smarttub-mqtt uses structured logging with automatic file rotation and ZIP compression.

## Log Files

Three separate log files are maintained:

- **mqtt.log**: MQTT broker connections, subscriptions, publications
- **webui.log**: Web UI requests, REST API calls
- **smarttub.log**: SmartTub API interactions, state management

## Log Rotation

When a log file reaches the configured maximum size (default: 5MB):

1. Current log file is closed
2. Any existing `.zip` for that log type is deleted
3. Log file is compressed to a new `.zip` (e.g., `mqtt.zip`)
4. Original rotated log is removed
5. Fresh log file is created

**Important**: Only **ONE** `.zip` file exists per log type. Old ZIPs are automatically deleted before creating new ones.

## Configuration

Log rotation is configured via environment variables in `/config/.env`:

```bash
# Log directory (default: /var/log/smarttub-mqtt)
LOG_DIR=/var/log/smarttub-mqtt

# Maximum log file size in MB before rotation (default: 5)
LOG_MAX_SIZE_MB=5

# Number of backup files (always 1 for ZIP mode)
LOG_MAX_FILES=1

# Enable ZIP compression (default: true)
LOG_COMPRESS=true

# Log level (default: INFO)
LOG_LEVEL=INFO
```

## YAML Configuration

Alternatively, configure in `config/smarttub.yaml`:

```yaml
logging:
  level: INFO
  log_dir: /var/log/smarttub-mqtt
  log_max_size_mb: 5
  log_max_files: 1
  log_compress: true
  mqtt_forwarding: false  # Optional: forward logs to MQTT
```

## Module Routing

Logs are automatically routed to appropriate files based on logger names:

- `smarttub.mqtt.*` → `mqtt.log`
- `smarttub.webui.*` → `webui.log`
- `smarttub.api.*` → `smarttub.log`
- Other loggers → All three files (root handler)

## MQTT Log Forwarding

### Overview

SmartTub-MQTT can optionally forward all structured logs to MQTT topics in real-time for remote monitoring and debugging.

### Enable Forwarding

Set `mqtt_forwarding: true` in configuration:

**Environment Variable:**
```bash
MQTT_LOG_FORWARDING=true
```

**YAML Configuration:**
```yaml
logging:
  mqtt_forwarding: true
```

### Log Topics

When enabled, logs are published to subsystem-specific topics:

```
smarttub-mqtt/meta/logs/smarttub  → SmartTub API logs (JSON)
smarttub-mqtt/meta/logs/mqtt      → MQTT broker logs (JSON)
smarttub-mqtt/meta/logs/webui     → Web UI logs (JSON)
```

### Log Message Format

Each log entry is published as JSON with full context:

```json
{
  "timestamp": "2025-10-30T14:32:01.123456Z",
  "level": "INFO",
  "logger": "smarttub.api.client",
  "event": "Polling spa state",
  "spa_id": "abc123",
  "poll_interval": 30
}
```

**Fields:**
- `timestamp`: ISO 8601 timestamp (UTC)
- `level`: DEBUG, INFO, WARNING, ERROR, CRITICAL
- `logger`: Logger name (module path)
- `event`: Log message/event description
- Additional context fields (spa_id, error details, etc.)

### Subscribing to Logs

#### All Logs (All Subsystems)

```bash
mosquitto_sub -t 'smarttub-mqtt/meta/logs/#' -v
```

#### Specific Subsystem

```bash
# SmartTub API only
mosquitto_sub -t 'smarttub-mqtt/meta/logs/smarttub' -v

# MQTT broker only
mosquitto_sub -t 'smarttub-mqtt/meta/logs/mqtt' -v

# Web UI only
mosquitto_sub -t 'smarttub-mqtt/meta/logs/webui' -v
```

#### Pretty Print with jq

```bash
mosquitto_sub -t 'smarttub-mqtt/meta/logs/#' | jq .
```

#### Filter by Log Level

```bash
# Only ERROR and CRITICAL
mosquitto_sub -t 'smarttub-mqtt/meta/logs/#' | \
  jq 'select(.level == "ERROR" or .level == "CRITICAL")'

# Only warnings and above
mosquitto_sub -t 'smarttub-mqtt/meta/logs/#' | \
  jq 'select(.level == "WARNING" or .level == "ERROR" or .level == "CRITICAL")'
```

### OpenHAB Integration

Subscribe to log streams in OpenHAB:

```java
// items/smarttub_logs.items
String SpaLastLog "Last Log Message" 
    { mqtt="<[broker:smarttub-mqtt/meta/logs/smarttub:state:JSONPATH($.event)]" }

String SpaLogLevel "Log Level [%s]" 
    { mqtt="<[broker:smarttub-mqtt/meta/logs/smarttub:state:JSONPATH($.level)]" }

String SpaLogTimestamp "Log Time" 
    { mqtt="<[broker:smarttub-mqtt/meta/logs/smarttub:state:JSONPATH($.timestamp)]" }
```

### Home Assistant Integration

Monitor logs in Home Assistant:

```yaml
# configuration.yaml
mqtt:
  sensor:
    - name: "SmartTub Last Log"
      state_topic: "smarttub-mqtt/meta/logs/smarttub"
      value_template: "{{ value_json.event }}"
      json_attributes_topic: "smarttub-mqtt/meta/logs/smarttub"
      json_attributes_template: "{{ value_json | tojson }}"
      icon: "mdi:text-box"
    
    - name: "SmartTub Log Level"
      state_topic: "smarttub-mqtt/meta/logs/smarttub"
      value_template: "{{ value_json.level }}"
      icon: "mdi:alert-circle"

  # Alert on errors
  automation:
    - alias: "SmartTub Log Error Alert"
      trigger:
        - platform: mqtt
          topic: "smarttub-mqtt/meta/logs/#"
      condition:
        - condition: template
          value_template: >
            {{ trigger.payload_json.level in ['ERROR', 'CRITICAL'] }}
      action:
        - service: notify.mobile_app
          data:
            title: "SmartTub Error"
            message: "{{ trigger.payload_json.event }}"
```

### Performance Impact

**Overhead:**
- CPU: ~5-10% additional for JSON serialization
- Network: ~1-5 KB/s depending on log level
- MQTT QoS: 0 (fire-and-forget, no delivery confirmation)

**Recommendation:** 
- Enable in **development/debugging** only
- Disable in **production** to reduce MQTT broker load
- Use file logs for long-term storage

### Troubleshooting MQTT Forwarding

#### No messages on log topics

1. Verify forwarding is enabled:
   ```bash
   docker exec smarttub-mqtt env | grep MQTT_LOG_FORWARDING
   ```

2. Check MQTT broker connection:
   ```bash
   mosquitto_sub -t 'smarttub-mqtt/meta/mqtt' -v
   ```

3. Increase log level to DEBUG:
   ```bash
   LOG_LEVEL=DEBUG
   docker restart smarttub-mqtt
   ```

#### Too many log messages

1. Reduce log level:
   ```bash
   LOG_LEVEL=WARNING  # Only warnings and errors
   ```

2. Disable forwarding:
   ```bash
   MQTT_LOG_FORWARDING=false
   docker restart smarttub-mqtt
   ```

## Example Log Entry

File format (plain text):
```
2025-01-15 14:32:01 - smarttub.mqtt.broker - INFO - Connected to MQTT broker
```

MQTT format (JSON):
```json
{
  "timestamp": "2025-01-15T14:32:01.123456Z",
  "level": "info",
  "event": "Connected to MQTT broker",
  "logger": "smarttub.mqtt.broker"
}
```

## Storage Management

With default settings (5MB max, 1 ZIP per type):

- Maximum disk usage: ~15MB active logs + ~15MB compressed ZIPs = **~30MB total**
- Logs older than one rotation are automatically discarded
- ZIP compression typically achieves 90%+ reduction

## Troubleshooting

### Common Issues

#### No log files created

**Symptom:** Log directory is empty

**Solutions:**

1. Check log directory permissions:
   ```bash
   ls -la /var/log/smarttub-mqtt/
   # Should be writable by smarttub user (UID 1000)
   ```

2. Verify directory exists:
   ```bash
   mkdir -p /var/log/smarttub-mqtt
   chown smarttub:smarttub /var/log/smarttub-mqtt
   ```

3. Check Docker volume mount:
   ```bash
   docker inspect smarttub-mqtt | grep -A 5 Mounts
   ```

#### Logs not rotating

**Symptom:** Log file exceeds `LOG_MAX_SIZE_MB`

**Solutions:**

1. Verify rotation configuration:
   ```bash
   docker exec smarttub-mqtt env | grep LOG_
   ```

2. Check disk space:
   ```bash
   df -h /var/log/smarttub-mqtt
   ```

3. Manually trigger rotation (restart container):
   ```bash
   docker restart smarttub-mqtt
   ```

#### ZIP compression not working

**Symptom:** `.log.1` files exist but no `.zip` files

**Solutions:**

1. Verify compression is enabled:
   ```bash
   docker exec smarttub-mqtt env | grep LOG_COMPRESS
   # Should be: LOG_COMPRESS=true
   ```

2. Check for Python zipfile module:
   ```bash
   docker exec smarttub-mqtt python -c "import zipfile"
   ```

3. Check file permissions:
   ```bash
   ls -la /var/log/smarttub-mqtt/
   ```

#### High disk usage

**Symptom:** Log directory using excessive space

**Solutions:**

1. Reduce log file size:
   ```bash
   LOG_MAX_SIZE_MB=2
   docker restart smarttub-mqtt
   ```

2. Clean old logs manually:
   ```bash
   # Remove all ZIPs
   rm /var/log/smarttub-mqtt/*.zip
   
   # Truncate current logs
   truncate -s 0 /var/log/smarttub-mqtt/*.log
   ```

3. Lower log level:
   ```bash
   LOG_LEVEL=WARNING
   docker restart smarttub-mqtt
   ```

#### Logs too verbose

**Symptom:** Too many DEBUG messages

**Solutions:**

1. Increase log level:
   ```bash
   LOG_LEVEL=INFO  # or WARNING
   docker restart smarttub-mqtt
   ```

2. Filter when reading:
   ```bash
   grep -E "WARNING|ERROR|CRITICAL" /var/log/smarttub-mqtt/smarttub.log
   ```

#### Cannot read ZIP files

**Symptom:** Cannot extract rotated logs

**Solutions:**

1. Install unzip utility:
   ```bash
   apt-get install unzip  # Debian/Ubuntu
   yum install unzip      # RHEL/CentOS
   ```

2. Extract manually:
   ```bash
   unzip /var/log/smarttub-mqtt/smarttub.zip
   cat smarttub.log.1
   ```

3. View without extracting:
   ```bash
   unzip -p /var/log/smarttub-mqtt/smarttub.zip | less
   ```

### Log Analysis

#### Count errors

```bash
# Count errors in active logs
grep -c ERROR /var/log/smarttub-mqtt/*.log

# Count errors in ZIPs
unzip -p /var/log/smarttub-mqtt/smarttub.zip | grep -c ERROR
```

#### Find recent errors

```bash
# Last 50 errors
grep ERROR /var/log/smarttub-mqtt/smarttub.log | tail -50

# Errors from last hour
find /var/log/smarttub-mqtt -name "*.log" -mmin -60 -exec grep ERROR {} +
```

#### Analyze patterns

```bash
# Group errors by type
grep ERROR /var/log/smarttub-mqtt/smarttub.log | \
  awk '{print $NF}' | sort | uniq -c | sort -rn

# Errors per hour
grep ERROR /var/log/smarttub-mqtt/smarttub.log | \
  awk '{print $1, $2}' | cut -d: -f1 | uniq -c
```

### Docker Logging

#### View container logs

```bash
# Follow logs
docker logs -f smarttub-mqtt

# Last 100 lines
docker logs --tail 100 smarttub-mqtt

# Since specific time
docker logs --since 30m smarttub-mqtt

# With timestamps
docker logs -t smarttub-mqtt
```

#### Export Docker logs

```bash
# Save to file
docker logs smarttub-mqtt > smarttub-docker.log 2>&1

# Filter errors only
docker logs smarttub-mqtt 2>&1 | grep ERROR > errors.log
```

## Implementation

See `src/core/log_rotation.py` for the custom `ZipRotatingFileHandler` implementation.

---

## MQTT Meta Topic

### Overview

smarttub-mqtt publishes comprehensive connection and interface information to a dedicated meta topic: `{base_topic}/meta/mqtt`

This topic is automatically updated on:
- Initial connection to MQTT broker
- Clean disconnections
- Connection failures and errors
- Reconnection attempts

### Topic Structure

**Topic:** `smarttub-mqtt/meta/mqtt` (retained)

**Payload Format:** JSON

```json
{
  "status": "connected",
  "broker": "mqtt://broker.example.com:1883",
  "client_id": "smarttub-mqtt-12345",
  "connection": {
    "connected": true,
    "uptime_seconds": 3600,
    "last_connect": "2025-01-15T14:32:01.123456+00:00",
    "last_disconnect": null,
    "reconnect_count": 0
  },
  "interface": {
    "version": "1.0.0",
    "protocol": "MQTT 3.1.1",
    "tls_enabled": false,
    "keepalive": 60,
    "qos_default": 1
  },
  "errors": {
    "last_error": null,
    "last_error_time": null,
    "error_count": 0
  }
}
```

### Field Descriptions

#### Status
- `connected`: MQTT broker connection is active
- `disconnected`: Clean disconnection (no errors)
- `error`: Connection failure or error condition

#### Connection Fields
- `connected`: Boolean indicating current connection state
- `uptime_seconds`: Time since last successful connection (0 if disconnected)
- `last_connect`: ISO 8601 timestamp of most recent connection
- `last_disconnect`: ISO 8601 timestamp of most recent disconnection (null if never disconnected)
- `reconnect_count`: Number of reconnections since initial connect

#### Interface Fields
- `version`: smarttub-mqtt version
- `protocol`: MQTT protocol version (typically "MQTT 3.1.1")
- `tls_enabled`: Whether TLS/SSL encryption is active
- `keepalive`: MQTT keepalive interval in seconds
- `qos_default`: Default Quality of Service level for publishes

#### Error Tracking
- `last_error`: Description of most recent error (null if none)
- `last_error_time`: ISO 8601 timestamp of most recent error
- `error_count`: Total count of errors since startup

### Use Cases

#### OpenHAB Monitoring
Create an MQTT Thing subscribing to `smarttub-mqtt/meta/mqtt` to display connection health in UI.

#### Alerting
Monitor `errors.error_count` to trigger alerts when errors accumulate.

#### Debugging
Check `connection.reconnect_count` to identify unstable network conditions.

### Retained Flag

The meta/mqtt topic is published with `retain=True`, ensuring:
- OpenHAB sees current status immediately on startup
- No need to wait for next connection event
- Last known state persists across restarts

### Implementation

See `src/mqtt/broker_client.py`:
- `publish_meta_mqtt()` method builds and publishes the topic
- Called automatically in `_handle_connect()` and `_handle_disconnect()`
- Error tracking integrated into `publish()` method

