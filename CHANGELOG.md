# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.2.1]: https://github.com/Habnix/smarttub-mqtt/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Habnix/smarttub-mqtt/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/Habnix/smarttub-mqtt/releases/tag/v0.1.2
