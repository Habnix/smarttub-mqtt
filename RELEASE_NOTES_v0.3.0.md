# Release v0.3.0 - Background Discovery

🎉 **Major Feature Release**: Automated Light Mode Discovery System

## 🚀 What's New

### Background Discovery System

SmartTub-MQTT can now automatically test which light modes your spa actually supports, saving you time and eliminating guesswork.

**Key Features:**
- 🔍 **Three Discovery Modes**: Choose between Full (~20 min), Quick (~5 min), or YAML-only (instant)
- 🌐 **WebUI Control**: User-friendly discovery page with live progress tracking
- 📡 **MQTT Control**: Start/stop discovery via MQTT commands
- ⚡ **Startup Automation**: Optional automatic discovery when container starts
- 💾 **Persistent Storage**: Results saved to YAML and published to MQTT
- 📊 **Real-time Progress**: Live progress updates with percentage completion

## 📋 Discovery Modes

| Mode | Duration | Modes Tested | Use Case |
|------|----------|--------------|----------|
| **YAML Only** | Instant | 0 (loads saved) | Reload existing results |
| **Quick** | ~5 min | 4 common modes | Quick verification |
| **Full** | ~20 min | All 18 modes | Complete discovery |

## 🎯 How to Use

### Via WebUI
1. Visit `http://<your-ip>:8000/discovery`
2. Select a mode (Quick recommended for first run)
3. Click "Start Discovery"
4. Watch the live progress bar

### Via MQTT
```bash
# Start quick discovery
mosquitto_pub -t 'smarttub-mqtt/discovery/control' \
  -m '{"action":"start","mode":"quick"}'

# Stop discovery
mosquitto_pub -t 'smarttub-mqtt/discovery/control' \
  -m '{"action":"stop"}'
```

### Automatic at Startup
```bash
# In .env file or docker-compose.yml
DISCOVERY_MODE=startup_quick
```

Options: `off` (default), `startup_quick`, `startup_full`, `startup_yaml`

## 📦 What's Included

### Core Components (Phase 1)
- **Discovery State Manager**: Thread-safe state management with observer pattern
- **Background Discovery Runner**: Non-blocking asyncio-based execution
- **Discovery Coordinator**: High-level API with singleton pattern

### MQTT Integration (Phase 2)
- **Discovery Topics**: 
  - `smarttub-mqtt/discovery/status` - Real-time status (not retained)
  - `smarttub-mqtt/discovery/control` - Command topic (start/stop)
  - `smarttub-mqtt/discovery/result` - Final results (retained)
- **MQTT Command Handler**: Remote discovery control via JSON commands

### WebUI Integration (Phase 3)
- **Discovery REST API**: 5 new endpoints
  - `GET /api/discovery/status` - Get current status
  - `POST /api/discovery/start` - Start discovery
  - `POST /api/discovery/stop` - Stop discovery
  - `GET /api/discovery/results` - Get results
  - `POST /api/discovery/reset` - Reset state
- **Discovery Page**: Interactive UI at `/discovery`
- **Navbar Link**: Added to main navigation

### Startup Integration (Phase 4)
- **YAML Fallback Publisher**: Publishes saved modes at startup
- **Conditional Discovery**: Startup automation via `DISCOVERY_MODE` env var

### Testing (Phase 5)
- ✅ **6 Unit Test Scripts**: Validation for each component
- ✅ **6 Integration Tests**: Complete workflow coverage
- ✅ **All Tests Passing**: 100% success rate

### Documentation (Phase 5)
- 📖 **Discovery Guide**: Comprehensive `docs/discovery.md` (200+ lines)
- 📖 **README Updates**: Background Discovery section
- 📖 **CHANGELOG**: Complete v0.3.0 entry

### Docker Support (Phase 6)
- 🐳 **Environment Variable**: `DISCOVERY_MODE` in docker-compose.yml
- 🐳 **Updated Examples**: Both docker-compose files updated
- 🐳 **Updated .env.example**: Full configuration examples

## 🔧 Technical Details

### MQTT Topic Structure
**Status Updates** (real-time, not retained):
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

**Final Results** (retained):
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

### Storage Format (YAML)
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
```

### Mode Detection
Each light mode is published to MQTT:
- **Topic**: `smarttub-mqtt/{spa_id}/light/{light_id}/meta/detected_modes`
- **Payload**: `OFF,ON,PURPLE,WHITE,HIGH_SPEED_COLOR_WHEEL`
- **Retained**: Yes (QoS 1)

## 📊 Performance

- **YAML Only**: < 1 second
- **Quick Mode**: ~5 minutes (4 modes × 8s/mode × lights)
- **Full Mode**: ~20 minutes (18 modes × 20s/mode × lights)
- **Startup Impact**: +0.5s for YAML loading (if file exists)

## 🔄 Migration Guide

### From v0.2.x

**No breaking changes!** All existing functionality remains unchanged.

**New Optional Features:**
1. **Environment Variable**: Add `DISCOVERY_MODE` to enable startup discovery
   ```bash
   DISCOVERY_MODE=off  # Default - no auto-discovery
   ```

2. **MQTT Topics**: Subscribe to `smarttub-mqtt/discovery/#` for discovery updates

3. **WebUI**: Visit `/discovery` page for interactive control

4. **YAML Publishing**: Detected modes automatically published at startup

### Fresh Install

Follow the [Quick Start](https://github.com/Habnix/smarttub-mqtt#quick-start-docker) in README.md

## 📝 Commits in This Release

1. `ac9963f` - Task 1.1: Discovery State Manager
2. `c854f31` - Task 1.2: Background Discovery Runner
3. `9873b89` - Task 1.3: Discovery Coordinator
4. `09b2d42` - Phase 2: MQTT Integration (Tasks 2.1 + 2.2)
5. `dc6b86a` - Phase 3: WebUI Integration (Tasks 3.1 + 3.2 + 3.3)
6. `05091b9` - Phase 4: Startup Integration (Tasks 4.1 + 4.2)
7. `fa80279` - docs: Phase 5.3 - Documentation for Background Discovery
8. `5161439` - feat: Phase 6.1 - Docker Environment Variables

## 📚 Documentation

- **Discovery Guide**: [docs/discovery.md](docs/discovery.md)
- **README**: Updated with Background Discovery section
- **CHANGELOG**: [CHANGELOG.md](CHANGELOG.md)

## 🙏 Acknowledgements

Thanks to the SmartTub community for feature requests and testing feedback.

Special thanks to Matt Zimmerman for the [python-smarttub](https://github.com/mdz/python-smarttub) library.

---

**Full Changelog**: https://github.com/Habnix/smarttub-mqtt/compare/v0.2.3...v0.3.0

## Download

- **Docker Image**: `docker pull willnix/smarttub-mqtt:0.3.0`
- **Source Code**: See Assets below
