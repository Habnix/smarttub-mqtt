# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-10-07

### Added
- Dedicated Docker Hub installation documentation and a release runbook
- A private Gitea Compose override using the development image
- Primary filtration control with `NORMAL`, `NANO_MODE` and `ECO_MODE`
- Read-only `cycleSpeed` reporting for color-changing lights
- Observable command lifecycle with command IDs and the states `accepted`,
  `sent`, `confirmed`, `failed`, and `unknown`
- Non-retained MQTT command results on
  `<base>/<spa_id>/commands/result`
- Explicit `live`, `stale`, and `unavailable` state quality metadata in the Web
  API and retained MQTT availability/quality topics
- Per-pump role, current speed, speed capability, and supported-speed metadata
- Configurable bounded command/publish queues and real buffer/drop/coalescing
  statistics
- A centralized `SmartTubGateway` compatibility boundary for every low-level
  upstream request
- An atomic recovery journal for hardware-mutating background light discovery
- Separate unauthenticated `/live` and dependency-aware `/ready` endpoints;
  `/health` remains as a compatibility liveness alias
- Exact production dependency lock, Python 3.13/3.14 CI matrix, and immutable
  wheel verification
- Machine-readable metadata and a generated migration reference for previously
  misleading configuration options
- A declarative 49-entry environment override schema with generated alias,
  parser, and boundary documentation
- A staged MyPy strictness ratchet for 17 stable core, command, and transport
  modules, enforced by CI and policy regression tests
- A monotonic, line-local broad-exception policy enforced by Ruff and tests
- A schema-versioned, path-centralized Discovery repository with atomic writes,
  concurrent update protection, and an in-memory snapshot for synchronous MQTT
  mapping
- Pure state, metadata, and discovery topic encoders plus an immutable MQTT
  message value object
- Central log redaction and value-free payload summaries for command and audit
  diagnostics
- One canonical application version shared by package metadata, FastAPI,
  CLI, MQTT metadata, and release OCI labels
- A console script entry point: `smarttub-mqtt`
- Starlette-compatible `httpx2` test dependency; the Python 3.14 project
  deprecation warning is no longer emitted

### Changed
- Public releases publish to Docker Hub; Gitea main builds keep publishing only
  the private `edge` image
- Release tags rerun the complete CI gate before publishing; signing credentials
  are checked before any image push and ARM64 builds use QEMU
- Public Compose deployments pin the new `0.4.0` image
- Migrated MQTT transport to `aiomqtt`
- Updated `python-smarttub` to `0.0.48` and Python support to 3.13+
- Removed obsolete migration notes and generated development artifacts
- HTTP command responses and command history now report the observable command
  state instead of claiming generic success
- State polling now treats status, pump, and light reads as one complete
  observation and preserves the last successful snapshot after read failures
- Pump toggles use the public upstream method with state read-back, including
  the LOW → HIGH → OFF sequence required by two-speed pumps
- Startup remains degraded during initial MQTT/SmartTub outages and recovers
  through background reconnect and polling
- Retained MQTT values coalesce while offline, command results remain ordered,
  subscriptions are restored, and shutdown receives a bounded drain period
- Capability refresh uses `CAPABILITY_REFRESH_INTERVAL` exactly
- Background discovery restores unfinished light state before accepting a new
  run and clears recovery records only after verified restoration
- Docker health checks use process liveness so temporary MQTT or SmartTub
  outages do not cause restart loops
- Docker installs the application as a wheel instead of an editable source tree;
  `python-smarttub` is pinned to the verified `0.0.48` commit
- Unauthenticated broad Web bindings emit a prominent trusted-LAN warning and
  the deployment documentation defines VPN/HTTPS-proxy requirements
- `WEB_UI_REFRESH_INTERVAL_SECONDS` now controls the dashboard polling interval;
  former no-op observability, retry, and automatic-discovery options emit a
  migration warning and are ignored for one compatibility cycle
- Configuration errors, parsing primitives, source loading, and environment
  overrides are separated from the application configuration dataclasses
- MyPy now checks bodies of untyped functions globally without a blanket
  missing-import exemption; command queues, async discovery callbacks, and
  required snapshot structure have explicit contracts
- Global Ruff exemptions for broad and silent exception handlers were removed;
  dotenv, version lookup, and Basic Auth now catch concrete exception types,
  while serializer fallbacks log instead of silently passing
- Discovery, recovery, Web, and CLI persistence now use one repository boundary;
  asynchronous callers offload filesystem work and MQTT snapshot mapping no
  longer performs synchronous YAML reads
- `MQTTTopicMapper` is now a compatibility facade over I/O-free encoders and a
  dedicated `MqttPublisher`, the only component that calls the broker transport
- State synchronization now has one explicit full-snapshot publication model;
  obsolete delta merging, duplicate update/recovery paths, pending-command
  storage, and misleading generic command reconciliation were removed
- MQTT command transitions now log structured correlation IDs, while command
  ingress and audit forwarding expose payload shape rather than payload values
- Project URLs now point to the actual GitHub repository; release workflows
  verify that the tag and canonical application version match
- The historical entries below retain their original release wording; a
  correction note documents paths and configuration statements that changed
  after those releases

### Fixed
- Updated locked `multidict` to 6.9.1 and `PyJWT` to 2.15.1 after the
  pre-release dependency audit reported vulnerabilities in the previous versions
- Propagate SmartTub pump and light command failures instead of recording them
  as successful commands
- Reject unknown component IDs and unsupported heat modes explicitly
- Preserve brightness `0` and zero-valued RGB channels
- Prevent light requests with an unresolved `None` zone
- Stop publishing synthetic heater-off and empty component states when the
  SmartTub API is unavailable
- Report LOW pumps as on/low and preserve unknown pump states and capabilities
  instead of coercing them to off/one-speed
- Stop assuming heater, pump, and light support when capability detection fails
- Reject command-queue overflow visibly and enforce command execution timeouts
- Resolve Web templates and static assets relative to the installed package so
  wheel execution works outside the repository working directory
- Prevent concurrent discovery writers from losing updates or exposing partial
  YAML files
- Prevent `CommandAuditLogger` from passing the structlog `event` argument twice
  and failing on its first audit event

## [0.3.3] - 2026-02-01

### Historical correction (2026-08-23)

The release notes above are retained as a record of the 0.3.3 release snapshot.
The current project contains `tests/`, `docs/`, and the discovery implementation
again; the old removal statement is not a description of the current tree.
Current discovery entry points are `src/mqtt/discovery_handler.py`,
`src/web/discovery_router.py`, and `docs/architecture.md`. The active
`SAFETY_COMMAND_TIMEOUT_SECONDS` option is documented in
`docs/configuration-reference.md` and `config/.env.example`; the older 0.2.0
note about removing it describes an intermediate historical configuration.

### Changed
- **Dependency Update**: Upgraded python-smarttub from 0.0.45 to 0.0.46
  - New authentication backend (Auth0 → SmartTub IDP)
  - Transparent migration, no code changes required
  - Endpoint: https://api.smarttub.io/idp/signin

### Fixed
- **Log Rotation**: Fixed OSError [Errno 9] Bad file descriptor
  - Added shouldRollover() override with error recovery
  - Safe stream handling in doRollover()
  - Prevents log rotation crashes in Docker environments

### Improved
- **Documentation**: Enhanced README with Docker Compose quick start guide
- **Project Structure**: Cleaned up development files for production deployment
- **Deployment**: Simplified docker-compose.yml for external MQTT broker setup

### Removed
- Development and test infrastructure (tests/, docs/, specs/)
- Legacy deployment examples (deploy/, mosquitto/, openhab/)
- Migration tools and obsolete configuration scripts

## [0.3.2] - 2025-11-16

### Fixed
- **CI Pipeline**: Added `[project.optional-dependencies]` section to `pyproject.toml`
  - Includes all dev dependencies (pytest, ruff, mypy, safety, bandit)
  - Fixed "collected 0 items" error in GitHub Actions
  - Updated CI workflow to use `pip install -e .[dev]`
- **Code Formatting**: Applied Ruff formatting to entire codebase (31 files)
  - Consistent code style across all Python files
  - No functional changes, only whitespace/formatting

### Changed
- Bumped version to 0.3.2 in pyproject.toml, Dockerfile, and version.py

## [0.3.1] - 2025-11-16

### Fixed
- **Discovery OFF Mode**: Critical bugfix for OFF mode testing
  - Fixed `AssertionError` when testing OFF mode (intensity must be 0, not 50)
  - Added conditional intensity: 0 for OFF mode, 50 for all other modes
- **YAML Data Preservation**: Fixed discovered_items.yaml overwriting device data
  - Discovery now merges detected_modes instead of replacing entire structure
  - Preserves pumps, heater, and spa metadata across discovery runs
- **Discovery Retry Mechanism**: Added 3-attempt retry loop for slow SmartTub API
  - Progressive delays: 20s, 25s, 30s between verification attempts
  - Improves reliability for slow API responses
- **Light Modes List**: Updated WebUI with official python-smarttub modes
  - Replaced deprecated modes (HIGH, BLUE_GREEN, ROTARY, etc.)
  - Now tests 18 official modes from python-smarttub library

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
  - Example: `smarttub-mqtt/<spa_id>/lights/zone_1/meta` now shows which modes were successfully tested
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
  - Old: `smarttub-mqtt/<spa_id>/meta/smarttub-mqtt`
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

[0.4.0]: https://github.com/Habnix/smarttub-mqtt/releases/tag/v0.4.0
[0.3.3]: https://github.com/Habnix/smarttub-mqtt/releases/tag/v0.3.3
[0.3.2]: https://github.com/Habnix/smarttub-mqtt/releases/tag/v0.3.2
[0.3.1]: https://github.com/Habnix/smarttub-mqtt/releases/tag/v0.3.1
[0.3.0]: https://github.com/Habnix/smarttub-mqtt/releases/tag/v0.3.0
[0.2.3]: https://github.com/Habnix/smarttub-mqtt/releases/tag/v0.2.3
[0.2.2]: https://github.com/Habnix/smarttub-mqtt/releases/tag/v0.2.2
[0.2.1]: https://github.com/Habnix/smarttub-mqtt/releases/tag/v0.2.1
[0.2.0]: https://github.com/Habnix/smarttub-mqtt/releases/tag/v0.2.0
[0.1.2]: https://github.com/Habnix/smarttub-mqtt/releases/tag/v0.1.2
