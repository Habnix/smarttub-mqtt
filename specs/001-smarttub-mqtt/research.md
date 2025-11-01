# Research: OpenHAB Whirlpool Integration

## python-smarttub API Coverage

- **Decision**: Use `python-smarttub`'s async client for polling, command execution, and capability discovery.
- **Rationale**: Library already models SmartTub authentication, exposes device states, and supports command endpoints with retries; aligns with project language requirements.
- **Alternatives Considered**:
  - Direct reverse engineering of SmartTub API (higher maintenance, security risk).
  - Custom fork of python-smarttub (unnecessary unless upstream gaps appear).

## MQTT Topic Strategy

- **Decision**: Mirror CarConnectivity topic pattern: `smarttub-mqtt/<component>/<metric>` for telemetry, `smarttub-mqtt/command/<component>` for controls, `smarttub-mqtt/meta/...` for discovery/logging.
- **Rationale**: Predictable namespace keeps OpenHAB items straightforward; discovery topics allow dynamic feature exposure; consistent with user's reference project for familiarity.
- **Alternatives Considered**:
  - Flat topic naming (harder to filter, less organized).
  - Separate telemetry/control root topics (adds configuration friction without clear benefit).

## Web UI Technology Stack

- **Decision**: Implement FastAPI for HTTP endpoints with Jinja2 templates for server-rendered dashboard plus HTMX for lightweight interactivity.
- **Rationale**: FastAPI integrates well with async python-smarttub workflow, supports OpenAPI generation, and allows reuse of contracts; Jinja2 keeps UI simple without SPA overhead.
- **Alternatives Considered**:
  - Flask (sync by default, less ergonomic with async SmartTub client).
  - Static HTML served via nginx (no dynamic updates or command submission).

## Logging and MQTT Bridging

- **Decision**: Use structlog for structured logging with configurable levels, streaming to stdout and optional MQTT topic `smarttub-mqtt/meta/logs` (JSON payloads).
- **Rationale**: structlog enables consistent metadata, easy filtering, and integration with Python logging. Publishing logs over MQTT satisfies remote monitoring requirement.
- **Alternatives Considered**:
  - Standard logging module only (harder to enforce structure, less flexible).
  - External log collector (overkill for local deployment).

## Docker Packaging

- **Decision**: Multi-stage Docker build using `python:3.11-slim` base, packaging app under `/app`, exposing config via mounted volume `/config` and `.env`, and publishing port 8080 for Web UI.
- **Rationale**: Slim image keeps footprint low; volume + env approach aligns with CarConnectivity reference; exposes minimal surface for OpenHAB integration.
- **Alternatives Considered**:
  - Alpine-based image (potential compatibility issues with python-smarttub dependencies).
  - Bundling MQTT broker inside container (violates single responsibility; user already manages broker).
