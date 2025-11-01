
# Feature Specification: SmartTub MQTT Bridge (OpenHAB/Pool)


## 1. Interface & Discovery

- The interface is based on the Python project [mdz/python-smarttub](https://github.com/mdz/python-smarttub). The full scope of the API is supported.
- On first start, or when `CHECK_SMARTTUB=true` is set in `/config/.env`, the integration probes the spa for all available settings. The discovered settings are stored/updated in `/config/discovered_items.yaml`.
- The YAML file is organized by spa identifier and contains information about heater, pumps, lights and general info under the `SPA` topic.

## 2. Configuration (.env)

The file `/config/.env` controls the project. Example:

```
SMARTTUB_EMAIL=my.email@email.com
SMARTTUB_PASSWORD=secret
SMARTTUB_DEVICE_ID=         # empty => autodetect
SMARTTUB_TOKEN=
SMARTTUB_POLLING_INTERVAL_SECONDS=15
SAFETY_POST_COMMAND_WAIT_SECONDS=12
SAFETY_COMMAND_VERIFICATION_RETRIES=3
SAFETY_COMMAND_TIMEOUT_SECONDS=7
MQTT_BROKER_URL=192.168.178.164:1883
MQTT_USERNAME=
MQTT_PASSWORD=
CONFIG_FILE=/config/smarttub.yaml
LOG_LEVEL=info
BASIC_AUTH_USERNAME=admin
BASIC_AUTH_PASSWORD=changeme
CHECK_SMARTTUB=true
```

## 3. Logging

The `/log` directory contains the following log files:
- `mqtt.log` (MQTT connection)
- `webui.log` (Web UI)
- `smarttub.log` (API / MQTT)

Log files are limited to 5MB. After that they are archived as a ZIP (`.zip`). Existing ZIPs are removed first so there is at most one `.log` and one `.zip` per type. The log contents are controlled by `LOG_LEVEL` (info, debug, error).

## 4. MQTT Topic Convention

Following the pattern used by [CarConnectivity-plugin-mqtt](https://github.com/tillsteinbach/CarConnectivity-plugin-mqtt):

```
smarttub-mqtt/<smarttub ID>/heater
smarttub-mqtt/<smarttub ID>/pumps
smarttub-mqtt/<smarttub ID>/lights
smarttub-mqtt/<smarttub ID>/spa
```

Under `pumps`/`lights`/`heater` each individual component is exposed as described in the YAML:
```
smarttub-mqtt/<smarttub ID>/pumps/P1
smarttub-mqtt/<smarttub ID>/pumps/CP
smarttub-mqtt/<smarttub ID>/lights/L1
smarttub-mqtt/<smarttub ID>/heater/H1
```

The `spa` topic contains general information (brand, name, email, JSON status payload).

Additionally:
```
smarttub-mqtt/mqtt
```
Contains information about the MQTT interface including errors and connection status.

**All topics deliver RAW data** (e.g. `Temperatur=29` without unit).

**Convention for writable values:**
- `<Value>` exposes the current API value.
- `<Value>_writetopic` is the value written by OpenHAB.
- For switches the API value and OpenHAB set value are separated using the same pattern.

## 5. Additional Requirements

- The Web UI is optional and can be protected with Basic Auth.
- The implementation must cover all features provided by the python-smarttub API.
- The discovery YAML is updated on each start when `CHECK_SMARTTUB=true`.

## 6. Questions

If further details or edge cases need clarification, please add them here.

## Clarifications

### Session 2025-10-23

- Q: Should the Web UI require authentication or trust the local network? → A: Make authentication configurable (default off, enable when needed).

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.

  Principle I requires that automated tests for each story are identified here. Describe the
  failing test you will author before implementation (unit, integration, MQTT contract).
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Monitor Whirlpool State in OpenHAB (Priority: P1)

As a homeowner, I want OpenHAB to display the real-time state of my whirlpool components so I can track heat, pumps, and lights without using the manufacturer app.

**Why this priority**: Monitoring provides immediate value, unlocks automations, and ensures the integration is trusted before control commands are allowed.

**Independent Test**: Create an integration test that stubs the manufacturer endpoint (via python-smarttub) to emit state changes and verifies OpenHAB items update within the SLA. Contract tests assert MQTT topics and payload schema.

**Acceptance Scenarios** *(include failure-handling paths per Principle II)*:

1. **Given** the whirlpool is connected, **When** the heater turns on, **Then** the corresponding OpenHAB item reflects "on" within 5 seconds.
2. **Given** the manufacturer endpoint temporarily drops the MQTT connection, **When** it reconnects, **Then** the system backfills the latest state and flags any missed updates in the event log.

---

### User Story 2 - Control Whirlpool Components with Confirmation (Priority: P2)

As a homeowner, I want to issue commands (e.g., start jets, adjust temperature) from OpenHAB and receive confirmation they were applied so I can manage the whirlpool remotely with confidence.

**Why this priority**: Control delivers the primary automation value once monitoring is stable; confirmation prevents unsafe or confusing states.

**Independent Test**: Write integration tests that send commands through OpenHAB MQTT topics and assert the manufacturer interface (python-smarttub) reports the new state within the SLA. Unit tests cover retry and rollback logic.

**Acceptance Scenarios**:

1. **Given** the whirlpool pump is off, **When** a user toggles the OpenHAB switch to "on", **Then** the project sends the command, receives manufacturer acknowledgment, and updates OpenHAB to confirmed success within 5 seconds.
2. **Given** a command fails due to manufacturer timeout, **When** retries are exhausted, **Then** the system reverts the OpenHAB item, surfaces an error message, and suggests verifying connectivity.

---

### User Story 3 - Auto-Detect Available Settings (Priority: P3)

As a homeowner, I want the integration to automatically detect which whirlpool settings are supported so I only see controls that apply to my model.

**Why this priority**: Reduces user confusion, prevents invalid commands, and supports multiple whirlpool configurations without manual tuning.

**Independent Test**: Develop discovery unit tests that read sample python-smarttub capability payloads and ensure only valid controls are exposed. End-to-end tests verify unsupported controls stay hidden in OpenHAB as well as the Web UI.

**Acceptance Scenarios**:

1. **Given** the whirlpool reports available features, **When** the integration initializes, **Then** only matching controls appear in OpenHAB and are labeled with friendly names.
2. **Given** the whirlpool firmware lacks a previously available feature, **When** the integration re-discovers capabilities, **Then** the control is removed from OpenHAB and a notice is logged.

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

- MQTT broker unreachable during polling → system queues missed polls, alerts user, and resumes safely on reconnect.
- Manufacturer payload returns conflicting sensor readings → system prioritizes most recent timestamp and flags discrepancy.
- Whirlpool reports unsupported feature → integration hides the control and records a telemetry event.
- Command acknowledged but state fails to change → system surfaces "pending" status and triggers manual intervention guidance.
- OpenHAB offline while state update arrives → integration buffers last-known state and replays when OpenHAB reconnects.


## Functional Requirements

- The system must implement all functions of the python-smarttub API and poll the state of all components regularly (configurable interval, default 15s).
- Discovery of available features occurs on startup or when `CHECK_SMARTTUB=true` and is saved to `/config/discovered_items.yaml`.
- MQTT topics follow the pattern `smarttub-mqtt/<ID>/<component>` and deliver RAW data.
- Writable values are exposed as `<Value>_writetopic`, API values as `<Value>`.
- Configuration is provided exclusively via `/config/.env`.
- Logging is written to `/log` with rotation and ZIP archiving after 5MB.
- The Web UI is optional and can be protected with Basic Auth.
- All relevant status and error information is published to the `smarttub-mqtt/mqtt` topic.

### Key Entities *(include if feature involves data)*

- **WhirlpoolComponent**: Represents a controllable or observable part of the tub (heater, pump, light); attributes include identifier, state value, allowable commands.
- **CapabilityProfile**: Describes the set of features reported by the whirlpool; attributes include feature name, supported commands, firmware version constraints.
- **StateSnapshot**: Captures the timestamped collection of component states; used for OpenHAB updates and historical logging.
- **ControlCommand**: Encapsulates a user-issued command from OpenHAB with desired state, retries attempted, and acknowledgment status.
- **LogEvent**: Represents a structured log message including level, timestamp, origin module, and optional exception payload.

### Documentation Requirements *(Principle III - mandatory)*

- **DOC-001**: Update README or feature docs explaining new commands/config options.
- **DOC-002**: Provide quickstart or usage snippets that demonstrate the user stories.
- **DOC-003**: Document any safety considerations and recovery procedures.
- **DOC-004**: Outline MQTT topic schema, logging level configuration, and Docker deployment instructions.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: 95% of state changes detected at the manufacturer interface appear in OpenHAB within 5 seconds during steady connectivity tests.
- **SC-002**: 90% of control commands issued from OpenHAB reach confirmed success or explicit failure within 7 seconds.
- **SC-003**: User acceptance testing confirms that first-time users can trigger a heating cycle via OpenHAB within three labeled actions.
- **SC-004**: Capability auto-discovery correctly enables or hides controls for at least 3 distinct whirlpool configurations during validation.
- **SC-005**: System logs provide sufficient detail for operators to diagnose command failures within 10 minutes without referencing source code.
- **SC-006**: Dockerized deployment can be started with a single documented command and reaches operational readiness (state sync + Web UI accessible) in under 2 minutes.

## Assumptions

- Whirlpool manufacturer interface is accessible on the local network and speaks a documented MQTT-based protocol.
- OpenHAB instance can subscribe to MQTT topics published by the project without additional authentication layers.
- Acceptable command confirmation window is under 7 seconds for typical whirlpool operations.
- Users will maintain network connectivity comparable to home Wi-Fi reliability; extended outages are considered out of scope.
- Users prefer configuration through environment variables + mounted files similar to CarConnectivity MQTT project.
