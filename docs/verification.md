# Verification & Testing Guide

Complete verification procedures for SmartTub-MQTT deployment, MQTT broker interoperability, and Web UI authentication.

## Overview

This guide covers:
- MQTT broker compatibility testing
- Web UI authentication validation
- End-to-end integration verification
- Production deployment checklist

## MQTT Broker Interoperability

SmartTub-MQTT is compatible with any MQTT 3.1.1 compliant broker. Tested with:

### Supported Brokers

| Broker | Version | Status | Notes |
|--------|---------|--------|-------|
| Eclipse Mosquitto | 2.0+ | ✅ Fully Tested | Recommended for production |
| EMQX | 5.0+ | ✅ Compatible | Enterprise features supported |
| HiveMQ | 4.0+ | ✅ Compatible | Cloud & on-premise |
| VerneMQ | 1.12+ | ⚠️ Compatible | Limited testing |
| RabbitMQ (MQTT Plugin) | 3.11+ | ⚠️ Compatible | Some QoS 2 limitations |

### Eclipse Mosquitto

**Installation:**

```bash
# Ubuntu/Debian
apt-get update
apt-get install mosquitto mosquitto-clients

# Docker
docker run -d -p 1883:1883 -p 9001:9001 \
  -v $(pwd)/mosquitto.conf:/mosquitto/config/mosquitto.conf \
  eclipse-mosquitto:2.0
```

**Configuration:**

```conf
# mosquitto.conf
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_type all
```

**Test Connection:**

```bash
# Subscribe to all topics
mosquitto_sub -h localhost -t '#' -v

# Publish test message
mosquitto_pub -h localhost -t 'test' -m 'Hello MQTT'

# Verify SmartTub topics
mosquitto_sub -h localhost -t 'smarttub-mqtt/#' -v
```

**Expected Topics:**

```
smarttub-mqtt/{spa_id}/status/online true
smarttub-mqtt/{spa_id}/heater/state ON
smarttub-mqtt/{spa_id}/heater/current_temperature 38.5
smarttub-mqtt/meta/mqtt {"status":"connected",...}
smarttub-mqtt/meta/errors {"error_summary":{...}}
smarttub-mqtt/meta/discovery {"overall_percent":100,...}
```

### EMQX

**Installation:**

```bash
# Docker
docker run -d --name emqx \
  -p 1883:1883 \
  -p 8083:8083 \
  -p 8084:8084 \
  -p 8883:8883 \
  -p 18083:18083 \
  emqx/emqx:5.0
```

**Dashboard:**

Access EMQX Dashboard at http://localhost:18083
- Default credentials: admin / public

**Configuration:**

```bash
# Configure SmartTub-MQTT
MQTT_BROKER=mqtt://localhost:1883
MQTT_QOS=1
MQTT_KEEPALIVE=60
```

**Verification:**

1. Open EMQX Dashboard → Clients
2. Verify `smarttub-mqtt` client connected
3. Check Topics → Should see `smarttub-mqtt/*` topics
4. Monitor Messages → Real-time message flow

**Expected Metrics:**

- Client Connected: Yes
- Messages Sent: > 0
- Messages Received: > 0 (if commands sent)
- Subscriptions: 1-3 (command topics)

### HiveMQ

**Cloud Setup:**

1. Sign up at https://www.hivemq.com/mqtt-cloud-broker/
2. Create cluster
3. Get connection details (host, port, username, password)

**Configuration:**

```bash
# .env
MQTT_BROKER=mqtt://your-cluster.hivemq.cloud:1883
MQTT_USERNAME=your-username
MQTT_PASSWORD=your-password
MQTT_QOS=1
```

**Test Connection:**

```bash
# Using MQTT Explorer or mosquitto_sub
mosquitto_sub -h your-cluster.hivemq.cloud \
  -p 1883 \
  -u your-username \
  -P your-password \
  -t 'smarttub-mqtt/#' -v
```

### VerneMQ

**Installation:**

```bash
# Docker
docker run -d --name vernemq \
  -p 1883:1883 \
  -e DOCKER_VERNEMQ_ACCEPT_EULA=yes \
  -e DOCKER_VERNEMQ_ALLOW_ANONYMOUS=on \
  vernemq/vernemq
```

**Configuration:**

```bash
MQTT_BROKER=mqtt://localhost:1883
```

**Verification:**

```bash
# Check VerneMQ status
docker exec vernemq vmq-admin cluster show

# Monitor sessions
docker exec vernemq vmq-admin session show
```

### RabbitMQ (MQTT Plugin)

**Installation:**

```bash
# Docker
docker run -d --name rabbitmq \
  -p 1883:1883 \
  -p 15672:15672 \
  rabbitmq:3.11-management

# Enable MQTT plugin
docker exec rabbitmq rabbitmq-plugins enable rabbitmq_mqtt
```

**Management UI:**

Access at http://localhost:15672
- Default credentials: guest / guest

**Configuration:**

```bash
MQTT_BROKER=mqtt://localhost:1883
MQTT_USERNAME=guest
MQTT_PASSWORD=guest
```

**Known Limitations:**

- QoS 2 not fully supported (use QoS 0 or 1)
- Retained messages may not persist across restarts

### Broker Compatibility Checklist

For any MQTT broker, verify:

- [ ] MQTT 3.1.1 protocol support
- [ ] QoS 0 and QoS 1 support
- [ ] Retained messages support (critical for state topics)
- [ ] Wildcard subscriptions (`smarttub-mqtt/#`)
- [ ] Topic length > 256 characters (for long spa IDs)
- [ ] Concurrent connections (if running multiple instances)
- [ ] Message size > 100 KB (for discovery JSON)
- [ ] TLS/SSL support (optional, for production)

## Web UI Authentication

SmartTub-MQTT supports optional HTTP Basic Authentication for the Web UI.

### Disable Authentication (Default)

**Configuration:**

```bash
# .env
WEB_AUTH_ENABLED=false
```

**Test:**

```bash
# Access without credentials
curl http://localhost:8080/

# Should return 200 OK with HTML
curl -i http://localhost:8080/
```

**Expected:**

```
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
...
<html>...</html>
```

### Enable Basic Authentication

**Configuration:**

```bash
# .env
WEB_AUTH_ENABLED=true
WEB_BASIC_AUTH_USERNAME=admin
WEB_BASIC_AUTH_PASSWORD=secure-password-123
```

**Restart:**

```bash
docker restart smarttub-mqtt
```

### Test Authentication

#### Health Check Endpoint (Always Public)

```bash
# Health endpoint should work WITHOUT auth
curl http://localhost:8080/health

# Expected: {"status":"healthy"}
```

#### Protected Endpoints (Require Auth)

```bash
# Without credentials - should fail
curl -i http://localhost:8080/

# Expected: 401 Unauthorized
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="SmartTub-MQTT"
```

#### With Valid Credentials

```bash
# With valid credentials
curl -u admin:secure-password-123 http://localhost:8080/

# Expected: 200 OK with HTML
HTTP/1.1 200 OK
...
<html>...</html>
```

#### With Invalid Credentials

```bash
# Wrong username
curl -u wrong:secure-password-123 -i http://localhost:8080/

# Wrong password
curl -u admin:wrong-password -i http://localhost:8080/

# Both should return 401 Unauthorized
HTTP/1.1 401 Unauthorized
```

### Browser Testing

1. **Disable Auth:**
   - Open http://localhost:8080
   - Should see dashboard immediately (no login prompt)

2. **Enable Auth:**
   - Open http://localhost:8080
   - Browser should prompt for username/password
   - Enter credentials
   - Should see dashboard after successful auth

3. **Invalid Credentials:**
   - Enter wrong username/password
   - Should see authentication prompt again
   - Check browser console for 401 errors

### API Endpoint Testing

```bash
# Test all API endpoints with auth

# 1. Health check (no auth required)
curl http://localhost:8080/health
# Expected: {"status":"healthy"}

# 2. State (auth required)
curl -u admin:secure-password-123 http://localhost:8080/api/state
# Expected: {"spas":[...]}

# 3. Capabilities (auth required)
curl -u admin:secure-password-123 http://localhost:8080/api/capabilities
# Expected: {"capabilities":{...}}

# 4. Errors (auth required)
curl -u admin:secure-password-123 http://localhost:8080/api/errors
# Expected: {"error_summary":{...}}

# 5. Discovery Progress (auth required)
curl -u admin:secure-password-123 http://localhost:8080/api/discovery/progress
# Expected: {"overall_percent":...}
```

### Security Validation

#### Timing Attack Protection

The authentication uses `secrets.compare_digest()` for constant-time comparison:

```python
# Test with identical strings (should succeed)
time curl -u admin:secure-password-123 http://localhost:8080/

# Test with different strings (should fail in same time)
time curl -u admin:wrong-password-123 http://localhost:8080/
time curl -u wrong:secure-password-123 http://localhost:8080/

# Response time should be similar (within ~10ms)
```

#### Password Complexity

Test with various password complexities:

```bash
# Weak password (not recommended but should work)
WEB_BASIC_AUTH_PASSWORD=123

# Strong password (recommended)
WEB_BASIC_AUTH_PASSWORD=Xy9#mK$pL2@qR8!vN4

# Very long password
WEB_BASIC_AUTH_PASSWORD=$(openssl rand -base64 32)
```

All should work correctly.

## End-to-End Integration Testing

### Test Scenario 1: Full Stack with Mosquitto

**Setup:**

```bash
cd deploy/
cp .env.example .env
# Edit .env with credentials
docker-compose up -d
```

**Verification Steps:**

1. **Check all containers running:**
   ```bash
   docker-compose ps
   # All should be "Up" and "healthy"
   ```

2. **Verify MQTT connection:**
   ```bash
   docker-compose exec mosquitto mosquitto_sub -t 'smarttub-mqtt/#' -C 10 -v
   # Should see topics published
   ```

3. **Test Web UI:**
   ```bash
   curl http://localhost:8080/health
   # Expected: {"status":"healthy"}
   ```

4. **Check SmartTub API:**
   ```bash
   docker-compose logs smarttub-mqtt | grep "Successfully authenticated"
   # Should see authentication success
   ```

5. **Verify discovery (if enabled):**
   ```bash
   docker-compose exec mosquitto \
     mosquitto_sub -t 'smarttub-mqtt/meta/discovery' -C 1 -v
   # Should see discovery progress
   ```

### Test Scenario 2: Command Execution

**Setup:**

Ensure SmartTub-MQTT is running and connected.

**Test Commands:**

```bash
# 1. Set heater temperature
mosquitto_pub -h localhost \
  -t 'smarttub-mqtt/{spa_id}/heater/target_temperature_writetopic' \
  -m '40'

# Wait 5-10 seconds for confirmation

# 2. Check state update
mosquitto_sub -h localhost \
  -t 'smarttub-mqtt/{spa_id}/heater/target_temperature' \
  -C 1 -v

# Expected: smarttub-mqtt/{spa_id}/heater/target_temperature 40
```

```bash
# 3. Control pump
mosquitto_pub -h localhost \
  -t 'smarttub-mqtt/{spa_id}/pumps/CP/state_writetopic' \
  -m 'HIGH'

# 4. Verify pump state
mosquitto_sub -h localhost \
  -t 'smarttub-mqtt/{spa_id}/pumps/CP/state' \
  -C 1 -v

# Expected: smarttub-mqtt/{spa_id}/pumps/CP/state HIGH
```

### Test Scenario 3: Error Recovery

**Simulate MQTT disconnect:**

```bash
# Stop MQTT broker
docker-compose stop mosquitto

# Check SmartTub logs
docker-compose logs -f smarttub-mqtt
# Should see connection errors and retry attempts

# Restart broker
docker-compose start mosquitto

# Verify reconnection
docker-compose logs smarttub-mqtt | grep "Connected to MQTT"
```

**Expected Behavior:**

1. SmartTub-MQTT detects disconnect
2. Publishes error to meta/errors (if broker comes back)
3. Attempts reconnection with backoff
4. Successfully reconnects when broker available
5. Resumes normal operation

### Test Scenario 4: Web UI Auth Toggle

**Test auth enable/disable without restart:**

```bash
# 1. Start without auth
WEB_AUTH_ENABLED=false docker-compose up -d smarttub-mqtt

# 2. Verify no auth required
curl http://localhost:8080/
# Expected: 200 OK

# 3. Enable auth
docker-compose exec smarttub-mqtt \
  sh -c 'echo "WEB_AUTH_ENABLED=true" >> /config/.env'

# 4. Restart
docker-compose restart smarttub-mqtt

# 5. Verify auth now required
curl -i http://localhost:8080/
# Expected: 401 Unauthorized

# 6. Test with credentials
curl -u admin:password http://localhost:8080/
# Expected: 200 OK
```

## Production Deployment Checklist

### Pre-Deployment

- [ ] SmartTub credentials verified (email + password/token)
- [ ] MQTT broker accessible and tested
- [ ] Docker/Docker Compose installed
- [ ] Firewall rules configured (ports 1883, 8080)
- [ ] SSL/TLS certificates obtained (if using HTTPS/MQTTS)
- [ ] Backup strategy defined
- [ ] Monitoring/alerting configured

### Configuration

- [ ] `.env` file created with all required variables
- [ ] Strong passwords set (min 16 characters)
- [ ] Web UI authentication enabled (`WEB_AUTH_ENABLED=true`)
- [ ] MQTT authentication configured (if broker requires)
- [ ] Log level set appropriately (`LOG_LEVEL=INFO`)
- [ ] Log rotation enabled (`LOG_COMPRESS=true`)
- [ ] Discovery mode disabled in production (`CHECK_SMARTTUB=false`)
- [ ] MQTT log forwarding disabled (`MQTT_LOG_FORWARDING=false`)

### Deployment

- [ ] `docker-compose up -d` successful
- [ ] All containers healthy (`docker-compose ps`)
- [ ] SmartTub API authentication successful
- [ ] MQTT broker connection established
- [ ] Web UI accessible
- [ ] Health check responding (`/health`)

### Post-Deployment

- [ ] MQTT topics published (`mosquitto_sub -t 'smarttub-mqtt/#'`)
- [ ] State updates appearing (temperature, pumps, etc.)
- [ ] Commands execute successfully (set temp, pump control)
- [ ] Error tracking functional (`/api/errors`)
- [ ] Logs rotating correctly (`ls /log/*.zip`)
- [ ] No critical errors in logs (`grep ERROR /log/*.log`)
- [ ] OpenHAB/Home Assistant integration tested

### Monitoring

- [ ] Health check endpoint monitored (uptime check)
- [ ] MQTT connection status tracked (`/meta/mqtt`)
- [ ] Error count monitored (`/meta/errors`)
- [ ] Disk space monitored (log directory)
- [ ] Container resource usage acceptable
- [ ] Alert triggers configured (errors, downtime)

### Security

- [ ] Web UI authentication enabled
- [ ] MQTT credentials not in git
- [ ] `.env` file secured (chmod 600)
- [ ] SSL/TLS enabled for MQTT (if public network)
- [ ] Firewall rules restrict access
- [ ] Regular security updates scheduled

## Troubleshooting Verification Issues

### MQTT Broker Connection Fails

```bash
# Check broker reachable
telnet localhost 1883

# Test with mosquitto_pub
mosquitto_pub -h localhost -t 'test' -m 'test'

# Check SmartTub logs
docker logs smarttub-mqtt | grep -i mqtt

# Verify credentials (if auth enabled)
docker exec smarttub-mqtt env | grep MQTT
```

### Web UI Not Accessible

```bash
# Check container running
docker ps | grep smarttub-mqtt

# Check port mapping
docker port smarttub-mqtt

# Test health check
curl http://localhost:8080/health

# Check logs
docker logs smarttub-mqtt | grep -i webui
```

### Auth Not Working

```bash
# Verify auth enabled
docker exec smarttub-mqtt env | grep WEB_AUTH

# Check credentials set
docker exec smarttub-mqtt env | grep WEB_BASIC_AUTH

# Test with curl verbose
curl -v -u admin:password http://localhost:8080/
```

### Topics Not Publishing

```bash
# Check SmartTub API connection
docker logs smarttub-mqtt | grep "Successfully authenticated"

# Verify MQTT broker connection
docker logs smarttub-mqtt | grep "Connected to MQTT"

# Check for errors
curl http://localhost:8080/api/errors | jq .

# Monitor all topics
mosquitto_sub -h localhost -t '#' -v
```

## Related Documentation

- [Configuration Guide](./configuration.md) - All configuration parameters
- [Deployment Guide](../deploy/README.md) - Docker deployment
- [Logging Guide](./logging.md) - Log configuration
- [Error Tracking](./error-tracking.md) - Error monitoring
- [Security Review](./security-review.md) - Security best practices

## Support

For verification issues:
- Review troubleshooting sections above
- Check [GitHub Issues](https://github.com/your-org/smarttub-mqtt/issues)
- Consult related documentation
