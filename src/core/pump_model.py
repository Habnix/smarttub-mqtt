"""Model-neutral normalization for SmartTub pump observations."""

from __future__ import annotations

from typing import Any


def enum_name(value: Any) -> str:
    """Return a stable uppercase representation without assuming an enum type."""
    raw = getattr(value, "name", value)
    return str(raw).strip().upper() if raw is not None else "UNKNOWN"


def normalize_pump_state(value: Any) -> tuple[str, str]:
    """Return public on/off state and currently observed speed."""
    raw_state = enum_name(value)
    if raw_state == "OFF":
        return "off", "off"
    if raw_state == "LOW":
        return "on", "low"
    if raw_state == "HIGH":
        return "on", "high"
    if raw_state == "ON":
        return "on", "unknown"
    return "unknown", "unknown"


def normalize_pump_role(value: Any) -> str:
    """Normalize the component role while retaining unknown vendor values."""
    return {
        "JET": "jet",
        "CIRCULATION": "circulation",
        "BLOWER": "blower",
    }.get(enum_name(value), "unknown")


def normalize_speed_capability(value: Any) -> str:
    """Normalize the API's pump speed-count/capability field."""
    raw_speed = enum_name(value).replace("-", "_").replace(" ", "_")
    if raw_speed in {"1", "ONE", "ONE_SPEED", "SINGLE", "SINGLE_SPEED"}:
        return "one_speed"
    if raw_speed in {"2", "TWO", "TWO_SPEED", "DUAL", "DUAL_SPEED"}:
        return "two_speed"
    return "unknown"


def supported_speeds(speed_capability: str) -> list[str]:
    """Return only speeds justified by an observed capability."""
    if speed_capability == "one_speed":
        return ["high"]
    if speed_capability == "two_speed":
        return ["low", "high"]
    return []
