<!--
Sync Impact Report
- Version change: (not set) → 1.0.0
- Modified principles: N/A (initial publication)
- Added sections: Core Principles, Engineering Guardrails, Workflow & Quality Gates, Governance
- Removed sections: None
- Templates requiring updates: ✅ .specify/templates/plan-template.md, ✅ .specify/templates/spec-template.md, ✅ .specify/templates/tasks-template.md
- Follow-up TODOs: None
-->

# SmartTub MQTT Constitution

## Core Principles

### I. Test-First Reliability
All production code MUST be preceded by automated tests that fail before implementation and pass after.
Continuous integration MAY NOT accept code when required tests fail or are missing. Test suites MUST cover
unit, integration, and MQTT contract scenarios relevant to a change. Rationale: The whirlpool controller must
operate unattended; preventing regressions is non-negotiable.

### II. Fail-Tolerant Control Paths
Control flows interacting with the tub MUST handle MQTT disconnects, sensor anomalies, and command retries
without crashing. Error paths MUST surface actionable diagnostics and default to safe tub states (e.g., stop
heating/pumps on ambiguity). Rationale: The environment is physical; resilience prevents equipment damage and
protects users.

### III. Documented Transparency
Every feature MUST ship with user-facing documentation (README updates, usage guides, or CLI help) and inline
developer notes where behavior is non-obvious. Docs MUST explain configuration, safety defaults, and how to run
tests locally and in CI. Rationale: The project targets public GitHub and Docker users who rely on clear docs to
operate safely.

### IV. Intuitive Operation
Interfaces (CLI, configuration files, dashboards) MUST favor simple defaults, self-describing commands, and
guardrails that prevent misconfiguration. UX validation MUST confirm common workflows (start/stop heat, set
temperature) remain discoverable and scriptable. Rationale: Ease of use drives adoption and reduces operational
mistakes.

## Engineering Guardrails

- Language: Python 3.11+ with typed modules; prefer standard library and well-supported MQTT clients (paho-mqtt).
- Testing Stack: pytest with coverage reporting ≥80% on touched files; include integration tests against a
	simulated MQTT broker.
- Deployment: Deliver container images with sane defaults; document environment variables; avoid bundling secrets.
- Security Posture: Local-first assumptions are acceptable, yet credentials stored in configs MUST support
	rotation and be excluded from version control via `.env` or secrets managers.

## Workflow & Quality Gates

1. Plan → Spec → Tasks sequence MUST reference this constitution and record how each principle is satisfied.
2. Code reviews MUST verify: tests exist and pass, failure handling is explicit, documentation changes accompany
	 behavior changes, and UX remains intuitive.
3. Releases MUST include a changelog entry summarizing tests executed and known limitations.
4. CI pipelines MUST run linting, type checks, unit, and integration suites; failures block merges.

## Governance

- Authority: This constitution supersedes prior informal practices for repository governance.
- Amendments: Proposals MUST document rationale, updated principles, and template impacts. Adoption requires
	maintainer approval and version bump per semantic rules (major = breaking governance, minor = new principle or
	major expansion, patch = clarifications).
- Compliance Reviews: Quarterly (or before major release) audits MUST confirm adherence to principles, test
	coverage, and documentation freshness. Non-compliance triggers remediation tasks tracked publicly.

**Version**: 1.0.0 | **Ratified**: 2025-10-23 | **Last Amended**: 2025-10-23
