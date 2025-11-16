# Migration Guide

## Upgrading to v1.0

### Overview

Version 1.0 brings comprehensive improvements in error handling, configuration validation, and observability. Most changes are backward compatible.

## Breaking Changes

### ❌ No breaking changes!

All existing configurations continue to work. New features are opt-in.

## Configuration Changes

### 1. Config Path

**Alt:**
```
smarttub.yaml  # Im Root-Verzeichnis
.env
```

**New (recommended):**
```
/config/smarttub.yaml
/config/.env
```

**Migration:**
```bash
mkdir -p /config
mv smarttub.yaml /config/
mv .env /config/
```

### 2. Renamed Parameters

| Alt | Neu | Default |
|-----|-----|---------|
| `logging.max_size_mb` | `logging.log_max_size_mb` | 5 |
| `logging.max_files` | `logging.log_max_files` | 5 |
| `logging.dir` | `logging.log_dir` | `/logs` (Docker) |

**Migration:**
```yaml
# Alt (funktioniert noch)
logging:
  max_size_mb: 10
  max_files: 7
  dir: /var/log/spa

# Neu (empfohlen für Docker)
logging:
  log_max_size_mb: 10
  log_max_files: 7
  log_dir: /logs
```

## New Features

### 1. Error Tracking

**Automatically enabled** - no configuration required.

**Subscribe to MQTT:**
```bash
mosquitto_sub -t "smarttub-mqtt/meta/errors"
```

**WebUI API:**
```bash
curl http://localhost:8080/api/errors
```

See [Error Tracking Guide](./error-tracking.md).

### 2. Discovery Progress

**Automatically enabled** - no configuration needed.

**Subscribe on MQTT:**
```bash
mosquitto_sub -t "smarttub-mqtt/meta/discovery"
```

**WebUI:**
Visit `http://localhost:8080/discovery` for live progress.

See [Discovery Progress Guide](./discovery-progress.md).

### 3. Configuration Validation

**Automatisch aktiviert** - alle Parameter werden validiert.

**Benefits:**
 - Clear error messages for invalid values
 - Type checking for all parameters
 - Range checks (min/max values)
 - Safe defaults

**Beispiel-Fehler:**
```
ConfigError: mqtt.qos must be between 0 and 2
ConfigError: web.port must be between 1 and 65535
ConfigError: smarttub.email is required
```

See [Configuration Guide](./configuration.md).

### 4. Enhanced Web UI

**Neue Features:**
- Error Log mit Filtering
- Discovery Progress Tracking
- Subsystem Health Status
- Live Logs
- Basic Authentication (optional)

**Enable Basic Auth:**
```bash
WEB_AUTH_ENABLED=true
WEB_AUTH_USERNAME=admin
WEB_AUTH_PASSWORD=changeme
```

### 5. Improved Logging

**Neue Parameter:**
```yaml
logging:
  log_compress: true           # Compress rotated logs
  mqtt_log_enabled: true       # Publish logs to MQTT
  mqtt_log_level: warning      # Min level for MQTT
```

**Log Rotation:**
- Automatische Rotation bei `log_max_size_mb`
- Behalte `log_max_files` rotierte Dateien
- Optional: Kompression mit gzip

## Docker Migration

### Old Docker Setup

```bash
docker run -v $(pwd)/config:/app/config smarttub-mqtt
```

### New Docker Setup

```bash
docker run -v /opt/smarttub-mqtt/config:/config smarttub-mqtt
```

**Migration:**
```bash
# 1. Erstelle neues Config-Verzeichnis
mkdir -p /opt/smarttub-mqtt/config

# 2. Kopiere alte Config
cp -r config/* /opt/smarttub-mqtt/config/

# 3. Update Docker Run Command
docker stop smarttub-mqtt
docker rm smarttub-mqtt
docker run -d \
  --name smarttub-mqtt \
  -v /opt/smarttub-mqtt/config:/config \
  -p 8080:8080 \
  smarttub-mqtt:latest
```

## Testing Your Migration

### 1. Validate Configuration

```bash
# Check config validity
python -m src.core.config_loader /config/smarttub.yaml
```

### 2. Check Logs

```bash
docker logs smarttub-mqtt | head -50
```

### 3. Verify MQTT Connection

```bash
mosquitto_sub -t "smarttub-mqtt/#" -v
```

### 4. Check Web UI

```bash
curl http://localhost:8080/api/errors
curl http://localhost:8080/api/discovery/progress
```

### 5. Monitor Errors

```bash
# Subscribe to error topic
mosquitto_sub -t "smarttub-mqtt/meta/errors" -v
```

## Rollback Plan

### If Issues Occur

1. **Stop new version:**
   ```bash
   docker stop smarttub-mqtt
   ```

2. **Restore old config:**
   ```bash
   cp /backup/smarttub.yaml /config/
   cp /backup/.env /config/
   ```

3. **Run old version:**
   ```bash
   docker run -d smarttub-mqtt:old-version
   ```

4. **Report issue** on GitHub

## Recommended Post-Migration

### 1. Enable Error Monitoring

**Home Assistant:**
```yaml
sensor:
  - platform: mqtt
    name: "SmartTub Errors"
    state_topic: "smarttub-mqtt/meta/errors"
    value_template: "{{ value_json.error_summary.total_errors }}"
    json_attributes_topic: "smarttub-mqtt/meta/errors"
    json_attributes_template: "{{ value_json | tojson }}"
```

**Node-RED:**
```json
{
  "id": "mqtt-in",
  "type": "mqtt in",
  "topic": "smarttub-mqtt/meta/errors",
  "qos": "1"
}
```

### 2. Configure Web UI Auth

```bash
# In /config/.env
WEB_AUTH_ENABLED=true
WEB_AUTH_USERNAME=admin
WEB_AUTH_PASSWORD=<strong-password>
```

### 3. Review Logs

```yaml
# In /config/smarttub.yaml
logging:
  level: info  # Start with info
  log_max_size_mb: 10
  log_max_files: 5
  mqtt_log_enabled: true
```

### 4. Monitor Discovery

Erste Discovery dauert 1-2 Minuten. Watch Progress:

```bash
watch -n 1 'curl -s http://localhost:8080/api/discovery/progress | jq .overall_percent'
```

### Upgrade Checklist

- [ ] Backup old configuration
- [ ] Move config to `/config/`
- [ ] Update renamed parameters
- [ ] Adjust Docker volume path
- [ ] Restart container
- [ ] Check logs for errors
- [ ] Verify MQTT connection
- [ ] Test Web UI
- [ ] Subscribe to error topic
- [ ] Monitor discovery progress
- [ ] Configure Basic Auth (optional)
- [ ] Delete old backups after 1 week

## Support

Bei Fragen oder Problemen:

- **GitHub Issues**: [Report Issue](https://github.com/your-org/smarttub-mqtt/issues)
- **Documentation**: [docs/](../)
- **Logs**: `docker logs smarttub-mqtt`

## Version History

### v1.0.0 (2025-10-30)

**Features:**
- ✅ Error Tracking & Recovery
- ✅ Discovery Progress Tracking
- ✅ Configuration Validation
- ✅ Enhanced Web UI
- ✅ Improved Logging
- ✅ Security Improvements

**Tests:**
- ✅ 58 Config Validation Tests
- ✅ 26 Error Tracking Tests
- ✅ 25 Discovery Progress Tests
- ✅ 109 Tests Total

**Documentation:**
- ✅ Configuration Guide
- ✅ Error Tracking Guide
- ✅ Discovery Progress Guide
- ✅ Security Review
- ✅ Migration Guide
- ✅ Testing Guide
