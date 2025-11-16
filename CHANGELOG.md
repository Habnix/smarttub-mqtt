# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2025-11-09

### Added - Background Discovery System

**Core Infrastructure**:
- **Discovery State Manager** (`src/core/discovery_state.py`): Thread-safe state management with observer pattern
  - Real-time state tracking (idle, running, completed, failed)
  - Progress monitoring with percentage calculation
  - Observable state changes for UI updates
- **Background Discovery Runner** (`src/core/background_discovery.py`): Non-blocking asyncio-based discovery execution
  - Three discovery modes: FULL (~20 min), QUICK (~5 min), YAML_ONLY (instant)
  - Graceful stop functionality
  - Async task management
- **Discovery Coordinator** (`src/core/discovery_coordinator.py`): High-level API with singleton pattern
  - Unified interface for all discovery operations
  - Automatic MQTT publishing
  - Error handling and recovery

**MQTT Integration**:
- **Discovery Topics**: New topic structure for discovery control and status
  - `smarttub-mqtt/discovery/status`: Real-time status updates (running/completed/failed)
  - `smarttub-mqtt/discovery/control`: Command topic (start/stop discovery)
  - `smarttub-mqtt/discovery/result`: Final results with detected modes (retained)
- **MQTT Command Handler** (`src/mqtt/discovery_mqtt_handler.py`): Remote discovery control
  - JSON-based commands: `{"action": "start", "mode": "quick"}`
  - Auto-subscription and message handling

**WebUI Integration**:
- **Discovery REST API** (`src/web/api/discovery_api.py`): 5 new endpoints
  - `GET /api/discovery/status`: Get current discovery status
  - `POST /api/discovery/start`: Start discovery (mode parameter)
  - `POST /api/discovery/stop`: Stop running discovery
  - `GET /api/discovery/results`: Get discovery results
  - `POST /api/discovery/reset`: Reset discovery state
- **Discovery WebUI Page** (`src/web/templates/discovery.html`): Interactive discovery interface
  - Mode selection cards (YAML Only, Quick, Full)
  - Live progress bar with percentage
  - Real-time status updates
  - Results display with detected modes
- **Navbar Integration**: Added "Discovery" link to main navigation

**Startup Integration**:
- **YAML Fallback Publisher** (`src/core/yaml_fallback.py`): Publish saved modes at startup
  - Automatically loads `discovered_items.yaml` on boot
  - Publishes `detected_modes` to MQTT for each light
  - Topic: `{base}/{spa}/lights/{light}/meta/detected_modes`
- **Conditional Discovery** (`src/cli/run.py`): Startup automation via environment variable
  - `DISCOVERY_MODE=off` (default): Manual discovery only
  - `DISCOVERY_MODE=startup_quick`: Quick discovery on startup
  - `DISCOVERY_MODE=startup_full`: Full discovery on startup
  - `DISCOVERY_MODE=startup_yaml`: YAML-only (instant) on startup

**Testing & Validation**:
- **Unit Tests**: 6 validation scripts covering all components
  - `tests/validate_discovery_state.py`: State management tests
  - `tests/validate_background_discovery.py`: Discovery runner tests
  - `tests/validate_discovery_coordinator_simple.py`: Coordinator API tests
  - `tests/validate_discovery_mqtt.py`: MQTT integration tests
  - `tests/validate_discovery_webui.py`: WebUI endpoint tests
  - `tests/validate_startup_integration.py`: Startup integration tests
- **Integration Tests** (`tests/integration/test_discovery_flow.py`): Complete workflow tests
  - Full discovery flow (start → progress → completion)
  - MQTT command handling
  - Concurrent operation prevention
  - Stop functionality
  - Error handling
  - State reset

**Documentation**:
- **Discovery Guide** (`docs/discovery.md`): Comprehensive 200+ line guide
  - Feature overview and discovery modes
  - Usage examples (WebUI, MQTT, API)
  - Configuration and troubleshooting
  - Performance considerations
  - Best practices
- **README Updates**: Background Discovery section with quick start
- **CHANGELOG**: This detailed changelog entry

### Changed
- **Main Application** (`src/cli/run.py`): Integrated discovery components
  - Initialize Discovery Coordinator after SmartTub client
  - YAML Fallback publishing on every startup
  - Conditional discovery based on DISCOVERY_MODE
  - Pass discovery_coordinator to FastAPI app
  - Graceful shutdown handling
- **MQTT Topics**: Changed `/light/` to `/lights/` for consistency across all components
- **Docker Configuration**: LOG_DIR default changed to `/logs` (was `/var/log/smarttub-mqtt`)

### Fixed
- **Docker Healthcheck**: Changed from curl to Python urllib for slim image compatibility
- **Exception Handler** (`src/cli/run.py`): Fixed indentation in exception handler
- **SmartTub API Access** (`src/core/background_discovery.py`): Use `spas` property instead of non-existent `get_account()` method
- **MQTT Discovery Control** (`src/mqtt/discovery_handler.py`): 
  - Handle both bytes and str payload types
  - Use `asyncio.run_coroutine_threadsafe()` with event loop for thread-safe async execution
  - Fixes "no event loop in thread" error from MQTT callbacks
- **Concurrent Start Prevention** (`src/core/background_discovery.py`): Added `_start_lock` to prevent race conditions

### Technical Details
- **Discovery Modes**:
  - FULL: Tests all 18 light modes, 20 seconds per mode, ~20 minutes total
  - QUICK: Tests 4 common modes (OFF, ON, PURPLE, WHITE), 8 seconds per mode, ~5 minutes total
  - YAML_ONLY: Loads saved results only, instant (<1 second)
- **Progress Tracking**:
  - Percentage calculation: `(modes_tested / modes_total) × 100`
  - Real-time updates via MQTT and WebUI
  - Tracks current spa, light, and mode being tested
- **Storage Format**: YAML with detected modes per light
  ```yaml
  discovered_items:
    spa-001:
      lights:
        - id: zone_1
          detected_modes: [OFF, ON, PURPLE, WHITE]
  ```
- **MQTT Payloads**:
  - Status: JSON with state, mode, progress object
  - Result: JSON with completion timestamp, YAML path, detected modes
  - Control: JSON commands (`{"action": "start", "mode": "quick"}`)
- **Thread Safety**: asyncio.Lock for concurrent access protection
- **Observer Pattern**: StateObserver interface for reactive updates

### Migration Notes
- **New Environment Variable**: `DISCOVERY_MODE` (optional)
  - Default: `off` (no change in behavior)
  - Set to `startup_quick` for automatic quick discovery
- **New MQTT Topics**: Subscribe to `smarttub-mqtt/discovery/#` for discovery updates
- **New WebUI Route**: `/discovery` page now available
- **Backward Compatible**: All existing functionality unchanged

### Performance Impact
- **Startup**: +0.5s for YAML loading (if file exists)
- **Runtime**: Minimal (discovery runs in background)
- **Discovery**: 5 min (quick) to 20 min (full) depending on mode

## [0.2.3] - 2025-11-09

### Added
- **Light mode detection in MQTT topics**: Added `detected_modes` field to light meta topics
  - Per-light meta topics now include `detected_modes: []` array from `discovered_items.yaml`
  - Example: `smarttub-mqtt/100946961/lights/zone_1/meta` now shows which modes were successfully tested
  - Enables OpenHAB/Home Assistant to know which modes are actually supported by the hardware
  - Falls back to empty array `[]` if no detection has been run yet

- **Version information system**: Centralized version management and display
  - New `src/core/version.py` module for version queries
  - MQTT topics: `smarttub-mqtt/meta/smarttub-mqtt` and `smarttub-mqtt/meta/python-smarttub`
  - WebUI navbar displays: "smarttub-mqtt: 0.2.3 | python-smarttub: 0.0.45"
  - Version topics are now global (not spa-specific) as they apply to entire system

- **Light modes capability tracking**: Enhanced capability detection for light features
  - `SpaCapabilities` class now includes `light_modes` field
  - Available modes loaded from `python-smarttub.SpaLight.LightMode` enum (18 modes)
  - WebUI light cards show available modes with badge display
  - Capability topic includes full mode list for integration configuration

### Changed
- **Version MQTT topic structure**: Moved from spa-specific to global
  - Old: `smarttub-mqtt/100946961/meta/smarttub-mqtt`
  - New: `smarttub-mqtt/meta/smarttub-mqtt`
  - Reasoning: Version information is system-wide, not spa-dependent

### Technical Details
- `detected_modes` loaded from YAML at runtime via `_load_detected_modes_for_light()`
- Searches for YAML in `/config/`, `config/`, and current directory
- Light meta topics are retained and published on every state update
- Empty `detected_modes: []` is normal before first light mode discovery run

## [0.2.2] - 2025-11-08

### Fixed
- **MQTT subscription persistence**: Subscriptions are now automatically restored after reconnect
  - Root cause: After MQTT disconnect/reconnect, topic subscriptions were not renewed
  - Solution: `_handle_connect` callback now resubscribes all registered topics
  - Result: Incoming MQTT commands (e.g., temperature, pump control) now work after reconnect

## [0.2.1] - 2025-11-08

### Fixed
- **WebUI startup crash**: Fixed "Directory 'src/web/static' does not exist" error
  - Static file mounting now checks if directory has content before mounting
  - WebUI starts successfully even with empty static directory

## [0.2.0] - 2025-11-08

### Added
- **Integrated python-smarttub library improvements**: Now using `light.set_mode()` with built-in state verification
- **Rate-limiting protection**: Automatic 429 "Too Many Requests" handling with exponential backoff (2s/4s/8s)
- **Spa online status check**: Discovery now verifies spa is online before testing modes
- **Dynamic mode intensity handling**: Correctly handles WHEEL and RGB modes that report 0% intensity
- **Improved logging**: Clear ✓/✗ symbols with "(verified)" indicator for successful state changes

### Changed
- **Simplified light mode discovery**: Removed ~80 lines of manual timing and retry logic
- **Reduced configuration complexity**: Removed `SAFETY_POST_COMMAND_WAIT_SECONDS`, `SAFETY_COMMAND_VERIFICATION_RETRIES`, and `SAFETY_COMMAND_TIMEOUT_SECONDS` from .env
- **Cleaner test scripts**: Updated `test_light_modes.py` to reflect that `set_mode()` now handles verification automatically
- **Increased discovery timing**: `LIGHT_TEST_DELAY_SECONDS` increased from 1s to 5s for reliable mode detection

### Fixed
- **Light mode discovery timing issue**: Discovery was testing modes too rapidly (1s intervals), causing API rejections
  - **Root cause**: SmartTub API needs processing time between mode changes
  - **Solution**: Increased delay to 5 seconds between tests
  - **Verification**: Live MQTT tests confirmed all modes work when properly spaced
- **State verification false negatives**: WHEEL/RGB modes report `intensity: 0` even when active, causing timeout failures
  - **Root cause**: Built-in verification expects intensity=100 but WHEEL/RGB modes always show 0%
  - **Solution**: Added manual verification after timeout - checks mode name only, ignores intensity
  - **Result**: Discovery now accurately detects supported modes (e.g., D1 Chairman supports WHEEL/RGB but not static colors)
- **Bidirectional MQTT communication**: Verified working in both directions (MQTT→Spa and Spa→MQTT)
- **State verification reliability**: Using library's built-in `_wait_for_state_change()` instead of manual polling
- **Zone isolation**: Improved reset between zone tests to prevent state conflicts

### Verified Test Results
- **Manual MQTT Control**: ✅ HIGH_SPEED_WHEEL, LOW_SPEED_WHEEL, FULL_DYNAMIC_RGB all functional
- **App→MQTT Sync**: ✅ Mode changes in SmartTub app immediately reflected in MQTT
- **MQTT→App Sync**: ✅ MQTT commands successfully control spa hardware
- **API Correctness**: ✅ Implementation verified against python-smarttub source code
- **Discovery Accuracy**: ✅ Correctly identifies spa-specific mode support (D1 Chairman: WHEEL/RGB ✓, static colors ✗)

### Known Limitations
- **Spa-specific mode support**: Not all spas support all light modes listed in the API
  - Example: D1 Chairman supports dynamic modes (WHEEL/RGB) but not static color modes (PURPLE, RED, etc.)
  - Discovery accurately detects which modes your specific spa model supports
  - API accepts unsupported modes without error, but spa hardware doesn't change state

### Technical Details
- **Discovery timing**: Increased from ~2 minutes to ~3 minutes (18 modes × 5s = 90s per zone)
- **Reliability improvement**: Proper timing prevents 400 Bad Request errors during automated discovery
- **Fallback mechanism**: Direct API calls with manual verification when `state.lights=None` bug occurs
- **Code reduction**: ~80 lines removed from `item_prober.py`, improved maintainability

## [0.1.2] - 2025-11-02

### Initial features
- MQTT bridge for SmartTub hot tubs
- Error tracking and recovery system
- Web UI dashboard
- Discovery and capability detection
- Multi-spa support
- Basic authentication
- Structured logging

[0.3.0]: https://github.com/Habnix/smarttub-mqtt/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/Habnix/smarttub-mqtt/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/Habnix/smarttub-mqtt/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Habnix/smarttub-mqtt/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Habnix/smarttub-mqtt/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/Habnix/smarttub-mqtt/releases/tag/v0.1.2
