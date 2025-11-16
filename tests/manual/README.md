# Manual Testing Guide for Background Discovery v0.3.0

This directory contains manual test scripts for verifying the Background Discovery functionality.

## Test Scripts

### `test_background_discovery_v0.3.0.sh`

Comprehensive test script that validates all Background Discovery features.

**What it tests:**
- ✅ WebUI endpoints (status, start, stop, results, reset)
- ✅ Discovery modes (YAML-only, Quick, Full)
- ✅ MQTT integration (topics and commands)
- ✅ YAML file generation and structure
- ✅ Startup modes (automatic discovery)
- ✅ Concurrent operation prevention
- ✅ Stop functionality
- ✅ State reset

**Prerequisites:**
```bash
# Required
docker
docker-compose
curl

# Optional (for enhanced testing)
jq                    # JSON parsing
mosquitto-clients     # MQTT tests (mosquitto_pub, mosquitto_sub)
```

**Usage:**
```bash
# Start your container first
cd /var/python/smarttub-mqtt
docker-compose up -d

# Run the test script
./tests/manual/test_background_discovery_v0.3.0.sh
```

**Configuration:**

The script uses environment variables for configuration:

```bash
# Default values (override as needed)
export MQTT_BROKER=localhost
export MQTT_PORT=1883
export MQTT_BASE_TOPIC=smarttub-mqtt
export WEB_URL=http://localhost:8080

# Then run
./tests/manual/test_background_discovery_v0.3.0.sh
```

## Test Categories

### 1. Quick Tests (< 1 minute)
- Container health check
- WebUI endpoint availability
- YAML-only discovery
- Stop functionality
- State reset
- Concurrent operation prevention

### 2. Medium Tests (~5 minutes)
- Quick discovery mode
- MQTT topic monitoring
- YAML file validation

### 3. Long Tests (~20 minutes)
- Full discovery mode (optional, prompted)
- Startup mode testing (optional, prompted)

## Expected Output

### Successful Test Run

```
============================================
Background Discovery v0.3.0 - Manual Test Script
============================================

============================================
Checking Prerequisites
============================================

✓ Docker installed
✓ docker-compose installed
✓ curl installed
✓ mosquitto_pub installed (MQTT tests enabled)
✓ jq installed (JSON parsing enabled)

============================================
Checking Container Status
============================================

[TEST 1] Container running?
✓ Container 'smarttub-mqtt' is running

[TEST 2] Container healthy?
✓ Container health: healthy

[TEST 3] WebUI accessible?
✓ WebUI accessible at http://localhost:8080

...

============================================
Test Summary
============================================

Total Tests:  25
Passed:       25
Failed:       0

🎉 All tests passed!
```

### Failed Test Example

```
[TEST 5] GET /api/discovery/status
✗ Status endpoint failed
ℹ Check container logs: docker logs smarttub-mqtt
```

## Troubleshooting

### Container Not Running

```bash
# Check container status
docker ps -a | grep smarttub-mqtt

# View logs
docker logs smarttub-mqtt

# Restart container
docker-compose restart
```

### WebUI Not Accessible

```bash
# Check if port is exposed
docker port smarttub-mqtt

# Check container health
docker inspect smarttub-mqtt | jq '.[0].State.Health'

# Check logs for errors
docker logs smarttub-mqtt --tail 100
```

### MQTT Tests Skipped

Install mosquitto-clients:

```bash
# Debian/Ubuntu
sudo apt-get install mosquitto-clients

# macOS
brew install mosquitto

# Alpine (Docker)
apk add mosquitto-clients
```

### Discovery Takes Too Long

- **Quick mode**: Should complete in ~5 minutes
  - If longer: Check SmartTub API connectivity
  - Check container logs for rate-limiting errors
  
- **Full mode**: Should complete in ~20 minutes
  - This is expected (18 modes × 20s × number of lights)
  - Can be stopped early with Ctrl+C or stop endpoint

### YAML File Not Found

```bash
# Check if file exists
docker exec smarttub-mqtt ls -la /config/discovered_items.yaml

# Run a discovery first
curl -X POST http://localhost:8080/api/discovery/start \
  -H "Content-Type: application/json" \
  -d '{"mode":"quick"}'
```

## Manual Testing Checklist

Use this checklist to manually verify features:

### WebUI Testing

- [ ] Visit `http://localhost:8080/discovery`
- [ ] Page loads without errors
- [ ] Mode selection cards visible (YAML Only, Quick, Full)
- [ ] Click "YAML Only" → "Start Discovery"
- [ ] Progress bar appears (should complete instantly)
- [ ] Results appear below with detected modes
- [ ] Click "Quick" → "Start Discovery"
- [ ] Progress bar updates in real-time
- [ ] Percentage increases from 0% to 100%
- [ ] Current spa/light updates
- [ ] Click "Stop Discovery" during execution
- [ ] Discovery stops gracefully
- [ ] Results preserved from previous run

### MQTT Testing

```bash
# Terminal 1: Subscribe to status
mosquitto_sub -h localhost -t 'smarttub-mqtt/discovery/status' -v

# Terminal 2: Subscribe to results
mosquitto_sub -h localhost -t 'smarttub-mqtt/discovery/result' -v

# Terminal 3: Send commands
# Start YAML-only
mosquitto_pub -t 'smarttub-mqtt/discovery/control' \
  -m '{"action":"start","mode":"yaml_only"}'

# Start quick
mosquitto_pub -t 'smarttub-mqtt/discovery/control' \
  -m '{"action":"start","mode":"quick"}'

# Stop
mosquitto_pub -t 'smarttub-mqtt/discovery/control' \
  -m '{"action":"stop"}'
```

**Verify:**
- [ ] Status messages appear in Terminal 1
- [ ] Result message appears in Terminal 2 after completion
- [ ] Commands in Terminal 3 trigger discovery

### Startup Mode Testing

```bash
# Test startup_yaml
echo "DISCOVERY_MODE=startup_yaml" >> config/.env
docker-compose restart
docker logs smarttub-mqtt | grep -i "yaml fallback"

# Test startup_quick
sed -i 's/startup_yaml/startup_quick/' config/.env
docker-compose restart
# Wait ~5 minutes, check logs

# Test startup_full (optional - takes ~20 minutes)
sed -i 's/startup_quick/startup_full/' config/.env
docker-compose restart
# Wait ~20 minutes, check logs

# Restore to off
sed -i '/DISCOVERY_MODE=/d' config/.env
docker-compose restart
```

**Verify:**
- [ ] YAML modes published at startup
- [ ] Quick/Full discovery runs automatically
- [ ] Progress visible in logs
- [ ] Results saved to YAML
- [ ] MQTT topics populated

### YAML File Testing

```bash
# View YAML file
docker exec smarttub-mqtt cat /config/discovered_items.yaml

# Check structure
docker exec smarttub-mqtt cat /config/discovered_items.yaml | grep "detected_modes:"

# Verify light zones
docker exec smarttub-mqtt cat /config/discovered_items.yaml | grep "zone:"
```

**Verify:**
- [ ] File exists after first discovery
- [ ] Contains `discovered_items:` root
- [ ] Contains spa IDs
- [ ] Contains lights array
- [ ] Contains `detected_modes` for each light
- [ ] Modes are valid (OFF, ON, PURPLE, etc.)

## Performance Benchmarks

Expected timing for different operations:

| Operation | Expected Time | Notes |
|-----------|--------------|-------|
| YAML-only discovery | < 1 second | Just loads file |
| Quick discovery (1 light) | ~30 seconds | 4 modes × 8s |
| Quick discovery (2 lights) | ~60 seconds | 4 modes × 8s × 2 |
| Full discovery (1 light) | ~6 minutes | 18 modes × 20s |
| Full discovery (2 lights) | ~12 minutes | 18 modes × 20s × 2 |
| Startup YAML publishing | < 1 second | On container start |
| API response time | < 100ms | All REST endpoints |
| MQTT status update | < 50ms | Real-time updates |

## Test Reports

After running tests, you can generate a simple report:

```bash
# Run tests and save output
./tests/manual/test_background_discovery_v0.3.0.sh > test_results.log 2>&1

# View summary
tail -20 test_results.log

# Count passed/failed
grep -c "✓" test_results.log
grep -c "✗" test_results.log
```

## Reporting Issues

If you find issues during testing:

1. **Capture logs:**
   ```bash
   docker logs smarttub-mqtt > logs.txt
   ```

2. **Capture test output:**
   ```bash
   ./tests/manual/test_background_discovery_v0.3.0.sh > test_output.txt 2>&1
   ```

3. **Capture configuration:**
   ```bash
   docker exec smarttub-mqtt cat /config/.env > config.txt
   docker exec smarttub-mqtt cat /config/discovered_items.yaml > discovered.yaml
   ```

4. **Create GitHub issue** with:
   - Test output
   - Container logs
   - Configuration (redact credentials!)
   - Expected vs actual behavior

## Next Steps

After successful testing:

1. **Review results:**
   - Check `discovered_items.yaml` for accuracy
   - Verify detected modes match your spa hardware
   - Test MQTT integration with your home automation

2. **Production deployment:**
   - Set appropriate `DISCOVERY_MODE` in `.env`
   - Configure auto-restart if needed
   - Monitor logs for first week

3. **Release to GitHub** (when ready):
   ```bash
   git push origin main
   git push origin v0.3.0
   ```

## Support

For help with testing:
- Check [docs/discovery.md](../../docs/discovery.md)
- Review [CHANGELOG.md](../../CHANGELOG.md)
- Open GitHub issue for bugs
