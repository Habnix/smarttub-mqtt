"""Small, transport-independent configuration parsing primitives."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.core.config_errors import ConfigError


def get_section(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    section = data.get(key, {})
    if section is None:
        return {}
    if not isinstance(section, Mapping):
        raise ConfigError(f"{key} section must be a mapping")
    return section


def require_str(data: Mapping[str, Any], key: str, namespace: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{namespace}.{key} is required")
    return value.strip()


def optional_non_empty(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"Expected string or null, received {type(value).__name__}")
    return value.strip() or None


def optional_string(value: Any, *, allow_empty: bool = True) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed and not allow_empty:
            return None
        return trimmed if trimmed or allow_empty else None
    raise ConfigError(f"Expected string or null, received {type(value).__name__}")


def coerce_int(
    value: Any,
    field_name: str,
    *,
    default: int | None = None,
    min_value: int | None = None,
) -> int:
    if value is None or value == "":
        if default is None:
            raise ConfigError(f"{field_name} is required")
        number = default
    elif isinstance(value, int):
        number = value
    elif isinstance(value, str):
        try:
            number = int(value.strip())
        except ValueError as exc:
            raise ConfigError(f"{field_name} must be an integer") from exc
    else:
        raise ConfigError(f"{field_name} must be an integer")

    if min_value is not None and number < min_value:
        raise ConfigError(f"{field_name} must be >= {min_value}")
    return number


def coerce_float(
    value: Any,
    field_name: str,
    *,
    default: float | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    if value is None or value == "":
        if default is None:
            raise ConfigError(f"{field_name} is required")
        number = default
    elif isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError as exc:
            raise ConfigError(f"{field_name} must be a number") from exc
    else:
        raise ConfigError(f"{field_name} must be a number")

    if min_value is not None and number < min_value:
        raise ConfigError(f"{field_name} must be >= {min_value}")
    if max_value is not None and number > max_value:
        raise ConfigError(f"{field_name} must be <= {max_value}")
    return number


def coerce_bool(value: Any, field_name: str, *, default: bool | None = None) -> bool:
    if value is None or value == "":
        if default is None:
            raise ConfigError(f"{field_name} is required")
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ConfigError(f"{field_name} must be a boolean value")
