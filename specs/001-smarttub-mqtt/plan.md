# Implementation Plan: Smarttub-MQTT

**Branch**: `001-smarttub-mqtt` | **Date**: 2025-10-23 | **Spec**: [spec.md](../spec.md)
**Input**: Feature specification from `/specs/001-smarttub-mqtt/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Bridge Python SmartTub with OpenHAB via MQTT to monitor and control whirlpool components, mirroring the
CarConnectivity MQTT architecture. Deliver realtime state sync, command confirmation, auto-discovery of supported
features, configurable logging (levels + MQTT forwarding), lightweight Web UI without persistence, and Dockerized
deployment with documented inputs/outputs.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.11 (per constitution guardrails)
**Primary Dependencies**: python-smarttub (OEM API), paho-mqtt (broker), FastAPI + Jinja2 (web UI + REST),
  uvicorn, python-dotenv, structlog for structured logging
**Storage**: No persistent storage (in-memory caches only)
**Testing**: pytest + pytest-asyncio, responses (HTTP mocking), mqtt simulate via hbmqtt or gmqtt test harness
**Target Platform**: Linux container (Docker) running alongside OpenHAB
**Project Type**: Single backend service with embedded web UI and MQTT gateway
**Performance Goals**: State propagation to OpenHAB <5s, command confirmation <7s, Web UI render <2s initial load
**Constraints**: Must operate offline-first on local network, keep memory footprint <256MB, zero data persistence
**Scale/Scope**: Single household whirlpool; MQTT topic namespace under `smarttub-mqtt/<component>/<metric>`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- ✅ Document the test strategy per user story, including how failing tests will be written first (Principle I).
- ✅ Describe how MQTT failures, retries, and safe-state fallbacks are handled (Principle II).
- ✅ Identify required documentation updates (README, quickstart, CLI help) for the planned work (Principle III).
- ✅ Capture UX expectations so common workflows stay simple and discoverable (Principle IV).

**Gate Evaluation (Pre-Design)**

- Principle I: Adopt fail-first pytest workflow enforced via CI; design includes contract tests for MQTT topics,
  integration tests for state and command flows, and unit coverage for capability discovery.
- Principle II: Plan provides reconnect/backoff logic for python-smarttub and MQTT clients, with safe-state rollback
  and alerting when confirmation fails.
- Principle III: Documentation set covers README, quickstart, CLI help, Web UI walkthrough, MQTT topic catalog,
  logging configuration, and Docker deployment guide.
- Principle IV: Web UI delivers simplified dashboard; configuration uses sensible defaults; MQTT topics adhere to
  predictable naming, ensuring intuitive use in OpenHAB.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
src/
├── core/
│   ├── smarttub_client.py
│   ├── state_manager.py
│   ├── capability_detector.py
│   └── config_loader.py
├── mqtt/
│   ├── broker_client.py
│   ├── topic_mapper.py
│   └── log_bridge.py
├── web/
│   ├── app.py
│   ├── templates/
│   └── static/
├── cli/
│   └── run.py
└── docker/
    └── entrypoint.py

tests/
├── unit/
│   ├── test_state_manager.py
│   ├── test_capability_detector.py
│   ├── test_topic_mapper.py
│   └── test_config_loader.py
├── integration/
│   ├── test_mqtt_bridge.py
│   ├── test_webui_state_flow.py
│   └── test_command_confirmation.py
└── contract/
    ├── test_mqtt_topics.py
    └── test_http_api.py
```

**Structure Decision**: Adopt single-service layout modeled after CarConnectivity MQTT project with dedicated
modules for SmartTub integration, MQTT gateway, and Web UI. Tests mirror constitution requirements (unit,
integration, contract) and ensure CLI + Docker entrypoints remain isolated.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| _None_ | | |

## Phase 0: Research & Unknown Resolution

### Objectives

- Validate python-smarttub supports required polling, command, and capability discovery operations.
- Adapt CarConnectivity MQTT topic and discovery strategy to whirlpool component taxonomy.
- Confirm FastAPI + Jinja web stack satisfies lightweight dashboard needs without persistence.
- Define structured logging approach with configurable levels and MQTT log forwarding.
- Establish Docker packaging requirements (base image, volumes, env vars, healthchecks) compatible with OpenHAB deployments.

### Research Tasks

1. Research python-smarttub API surface for state polling, command issuing, and feature metadata.
2. Analyze CarConnectivity-plugin-mqtt to derive topic naming, discovery handshake, and configuration patterns.
3. Evaluate lightweight Web UI approaches (FastAPI/Jinja vs. alternative) focusing on live state display and command triggers.
4. Gather best practices for publishing logs and configuration topics over MQTT, including QoS/retain policies.
5. Review Docker deployment patterns for home automation services to document image build and runtime interfaces.

### Deliverable

- `/var/python/smarttub-mqtt/specs/001-smarttub-mqtt/research.md` capturing decisions, rationales, and alternatives for each research task.

## Phase 1: Design & Contracts

**Prerequisite**: research.md approved.

### Artifacts

1. `data-model.md` – Entity definitions (WhirlpoolComponent, CapabilityProfile, StateSnapshot, ControlCommand, LogEvent), validation rules, and state diagrams.
2. `contracts/openapi.yaml` – REST API for Web UI backing services (`GET /api/state`, `GET /api/capabilities`, `POST /api/commands`, `GET /api/logs`).
3. `contracts/mqtt-topics.md` – Topic catalog specifying publish/subscribe subjects, payload schemas, QoS, retain behavior, and discovery handshake.
4. `quickstart.md` – Local + Docker setup, configuration walkthrough, testing commands, MQTT broker integration, Web UI usage, troubleshooting.
5. Agent context update via `.specify/scripts/bash/update-agent-context.sh copilot` to register new technologies.

### Design Activities

- Derive module boundaries for smarttub client, state manager, command processor, MQTT bridge, Web UI, logging bridge, and Docker entrypoint.
- Specify retry/backoff and safe-state logic for SmartTub API and MQTT interactions.
- Map capability discovery outputs to OpenHAB item definitions and Web UI component visibility.
- Define configuration schema (YAML/env) covering MQTT broker, polling interval, log levels, web auth (if any), Docker volume paths.
- Design logging pipeline (structlog processors, stdout formatting, MQTT forwarding topics) with level filtering.

### Constitution Re-check (Post-Design)

- Principle I: Ensure test plan includes contract coverage for MQTT/HTTP APIs, integration tests for command lifecycle, unit tests for discovery + logging.
- Principle II: Document fallback behaviors for connectivity loss and command failure, including user notifications.
- Principle III: Verify documentation artifacts cover all user-facing surfaces (CLI, Web UI, MQTT map, Docker usage).
- Principle IV: Review Web UI wireframes and topic naming to guarantee intuitive operation and minimal configuration.

## Phase 2 Preview (Implementation Planning)

- Identify `/speckit.tasks` focus areas: foundational infrastructure (config + clients), monitoring pipeline, command pipeline, capability discovery, Web UI rendering, logging & MQTT bridge, Docker packaging.
- Sequence work to honor constitution gate: tests first (contract/unit/integration) preceding implementation per module.
- Note dependencies for future tasks: mock python-smarttub fixtures, local MQTT broker setup script, static assets for Web UI, Docker base image selection.
