"""Declarative environment-variable schema and override application."""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from src.core.config_errors import ConfigError
from src.core.config_parsing import (
    coerce_bool,
    coerce_float,
    coerce_int,
    optional_non_empty,
    optional_string,
)
from src.core.config_registry import DEPRECATED_BY_ENV, ConfigOption

ParserKind = Literal[
    "bool",
    "float",
    "ignore_empty",
    "int",
    "lower",
    "optional",
    "optional_non_empty",
    "required",
    "string",
    "unsupported_token",
]


@dataclass(frozen=True)
class EnvOverride:
    """One ordered mapping from an environment variable to an object attribute."""

    env_name: str
    target: str | None
    parser: ParserKind
    yaml_path: str | None = None
    min_value: float | None = None
    max_value: float | None = None


# Order is intentional: later aliases retain their historic precedence.
ENV_OVERRIDES: tuple[EnvOverride, ...] = (
    EnvOverride("SMARTTUB_EMAIL", "smarttub.email", "required", "smarttub.email"),
    EnvOverride("CHECK_SMARTTUB", "check_smarttub", "bool"),
    EnvOverride(
        "DISCOVERY_TEST_ALL_LIGHT_MODES", "discovery_test_all_light_modes", "bool"
    ),
    EnvOverride(
        "SMARTTUB_PASSWORD",
        "smarttub.password",
        "optional_non_empty",
        "smarttub.password",
    ),
    EnvOverride("SMARTTUB_TOKEN", None, "unsupported_token", "smarttub.token"),
    EnvOverride(
        "SMARTTUB_DEVICE_ID", "smarttub.device_id", "ignore_empty", "smarttub.device_id"
    ),
    EnvOverride(
        "SMARTTUB_POLLING_INTERVAL_SECONDS",
        "smarttub.polling_interval_seconds",
        "int",
        "smarttub.polling_interval_seconds",
        min_value=1,
    ),
    EnvOverride(
        "SMARTTUB_MAX_RETRIES",
        "smarttub.max_retries",
        "int",
        "smarttub.max_retries",
        min_value=0,
    ),
    EnvOverride(
        "SMARTTUB_RETRY_BACKOFF_SECONDS",
        "smarttub.retry_backoff_seconds",
        "int",
        "smarttub.retry_backoff_seconds",
        min_value=1,
    ),
    EnvOverride(
        "POLL_INTERVAL",
        "smarttub.polling_interval_seconds",
        "int",
        "smarttub.polling_interval_seconds",
        min_value=1,
    ),
    EnvOverride(
        "POLL_MIN_INTERVAL",
        "smarttub.poll_min_interval_seconds",
        "int",
        "smarttub.poll_min_interval_seconds",
        min_value=1,
    ),
    EnvOverride(
        "STATE_UPDATE_DELAY_SECONDS",
        "smarttub.state_update_delay_seconds",
        "float",
        "smarttub.state_update_delay_seconds",
        min_value=0.5,
        max_value=10.0,
    ),
    EnvOverride("MQTT_BROKER_URL", "mqtt.broker_url", "required", "mqtt.broker_url"),
    EnvOverride("MQTT_USERNAME", "mqtt.username", "optional", "mqtt.username"),
    EnvOverride("MQTT_PASSWORD", "mqtt.password", "optional", "mqtt.password"),
    EnvOverride("MQTT_CLIENT_ID", "mqtt.client_id", "ignore_empty", "mqtt.client_id"),
    EnvOverride("MQTT_BASE_TOPIC", "mqtt.base_topic", "required", "mqtt.base_topic"),
    EnvOverride("MQTT_QOS", "mqtt.qos", "int", "mqtt.qos", min_value=0),
    EnvOverride("MQTT_RETAIN", "mqtt.retain", "bool", "mqtt.retain"),
    EnvOverride(
        "MQTT_KEEPALIVE", "mqtt.keepalive", "int", "mqtt.keepalive", min_value=10
    ),
    EnvOverride(
        "MQTT_PUBLISH_QUEUE_SIZE",
        "mqtt.publish_queue_size",
        "int",
        "mqtt.publish_queue_size",
        min_value=1,
    ),
    EnvOverride(
        "MQTT_PUBLISH_DRAIN_TIMEOUT_SECONDS",
        "mqtt.publish_drain_timeout_seconds",
        "int",
        "mqtt.publish_drain_timeout_seconds",
        min_value=1,
    ),
    EnvOverride("LOG_LEVEL", "logging.level", "lower", "logging.level"),
    EnvOverride(
        "LOG_MQTT_FORWARDING",
        "logging.mqtt_forwarding",
        "bool",
        "logging.mqtt_forwarding",
    ),
    EnvOverride(
        "LOG_STDOUT_FORMAT",
        "logging.stdout_format",
        "required",
        "logging.stdout_format",
    ),
    EnvOverride("LOG_FILE_PATH", "logging.file_path", "optional", "logging.file_path"),
    EnvOverride("LOG_DIR", "logging.log_dir", "string", "logging.log_dir"),
    EnvOverride(
        "LOG_MAX_SIZE_MB",
        "logging.log_max_size_mb",
        "int",
        "logging.log_max_size_mb",
        min_value=1,
    ),
    EnvOverride(
        "LOG_MAX_FILES",
        "logging.log_max_files",
        "int",
        "logging.log_max_files",
        min_value=1,
    ),
    EnvOverride("LOG_COMPRESS", "logging.log_compress", "bool", "logging.log_compress"),
    EnvOverride(
        "LOG_MQTT_ENABLED",
        "logging.mqtt_log_enabled",
        "bool",
        "logging.mqtt_log_enabled",
    ),
    EnvOverride(
        "LOG_MQTT_LEVEL", "logging.mqtt_log_level", "lower", "logging.mqtt_log_level"
    ),
    EnvOverride("WEB_HOST", "web.host", "required", "web.host"),
    EnvOverride("WEB_ENABLED", "web.enabled", "bool", "web.enabled"),
    EnvOverride("WEB_PORT", "web.port", "int", "web.port", min_value=1),
    EnvOverride("WEB_AUTH_ENABLED", "web.auth_enabled", "bool", "web.auth_enabled"),
    EnvOverride(
        "BASIC_AUTH_USERNAME",
        "web.basic_auth_username",
        "optional",
        "web.basic_auth_username",
    ),
    EnvOverride(
        "WEB_AUTH_USERNAME",
        "web.basic_auth_username",
        "optional",
        "web.basic_auth_username",
    ),
    EnvOverride(
        "BASIC_AUTH_PASSWORD",
        "web.basic_auth_password",
        "optional",
        "web.basic_auth_password",
    ),
    EnvOverride(
        "WEB_AUTH_PASSWORD",
        "web.basic_auth_password",
        "optional",
        "web.basic_auth_password",
    ),
    EnvOverride(
        "WEB_UI_REFRESH_INTERVAL_SECONDS",
        "web_ui.refresh_interval_seconds",
        "int",
        "web_ui.refresh_interval_seconds",
        min_value=1,
    ),
    EnvOverride(
        "SAFETY_COMMAND_TIMEOUT_SECONDS",
        "safety.command_timeout_seconds",
        "int",
        "safety.command_timeout_seconds",
        min_value=1,
    ),
    EnvOverride(
        "SAFETY_COMMAND_QUEUE_SIZE",
        "safety.command_queue_size",
        "int",
        "safety.command_queue_size",
        min_value=1,
    ),
    EnvOverride(
        "DOCKER_CONFIG_VOLUME",
        "docker.config_volume",
        "required",
        "docker.config_volume",
    ),
    EnvOverride("DOCKER_ENV_FILE", "docker.env_file", "required", "docker.env_file"),
    EnvOverride(
        "DOCKER_HEALTHCHECK_INTERVAL_SECONDS",
        "docker.healthcheck_interval_seconds",
        "int",
        "docker.healthcheck_interval_seconds",
        min_value=1,
    ),
    EnvOverride(
        "CAPABILITY_CACHE_EXPIRY_SECONDS",
        "capability.cache_expiry_seconds",
        "int",
        "capability.cache_expiry_seconds",
        min_value=60,
    ),
    EnvOverride(
        "CAPABILITY_REFRESH_INTERVAL",
        "capability.refresh_interval_seconds",
        "int",
        "capability.refresh_interval_seconds",
        min_value=60,
    ),
    EnvOverride(
        "CAPABILITY_REFRESH_INTERVAL_SECONDS",
        "capability.refresh_interval_seconds",
        "int",
        "capability.refresh_interval_seconds",
        min_value=60,
    ),
)


def apply_env_overrides(config: Any, env: Mapping[str, str]) -> None:
    """Apply present variables using the ordered declarative schema."""
    _warn_deprecated_env_options(env)
    for option in ENV_OVERRIDES:
        if option.env_name not in env:
            continue
        value = _parse(option, env[option.env_name])
        if option.parser == "ignore_empty" and value is None:
            continue
        if option.target is not None:
            _set_target(config, option.target, value)


def render_env_override_reference() -> str:
    """Render active Env aliases, targets, parsers, and declared boundaries."""
    lines = [
        "## Active environment override schema",
        "",
        "Entries are applied from top to bottom. If aliases target the same field,",
        "the later present alias wins.",
        "",
        "| Environment | YAML path / target | Parser | Bounds |",
        "|---|---|---|---|",
    ]
    for option in ENV_OVERRIDES:
        target = option.yaml_path or option.target or "—"
        bounds = []
        if option.min_value is not None:
            bounds.append(f">= {option.min_value:g}")
        if option.max_value is not None:
            bounds.append(f"<= {option.max_value:g}")
        lines.append(
            f"| `{option.env_name}` | `{target}` | `{option.parser}` | "
            f"{' / '.join(bounds) or '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


def _parse(option: EnvOverride, raw: str) -> Any:
    if option.parser == "unsupported_token":
        raise ConfigError(
            "SMARTTUB_TOKEN is not supported; configure SMARTTUB_PASSWORD instead"
        )
    if option.parser == "bool":
        return coerce_bool(raw, option.env_name)
    if option.parser == "int":
        return coerce_int(raw, option.env_name, min_value=_int_bound(option.min_value))
    if option.parser == "float":
        return coerce_float(
            raw,
            option.env_name,
            min_value=option.min_value,
            max_value=option.max_value,
        )
    if option.parser == "optional":
        return optional_string(raw)
    if option.parser == "optional_non_empty":
        return optional_non_empty(raw)
    if option.parser == "ignore_empty":
        return raw.strip() or None
    if option.parser in {"required", "lower"}:
        value = raw.strip()
        if not value:
            raise ConfigError(f"{option.env_name} cannot be empty")
        return value.lower() if option.parser == "lower" else value
    return raw.strip()


def _int_bound(value: float | None) -> int | None:
    return int(value) if value is not None else None


def _set_target(config: Any, target: str, value: Any) -> None:
    parts = target.split(".")
    owner = config
    for part in parts[:-1]:
        owner = getattr(owner, part)
    setattr(owner, parts[-1], value)


def _warn_deprecated_env_options(env: Mapping[str, str]) -> None:
    for env_name, option in DEPRECATED_BY_ENV.items():
        if env_name in env:
            warn_deprecated_option(env_name, option)


def warn_deprecated_option(name: str, option: ConfigOption) -> None:
    replacement = f" {option.replacement}" if option.replacement else ""
    warnings.warn(
        f"Configuration option {name} is deprecated and ignored.{replacement}",
        FutureWarning,
        stacklevel=3,
    )
