from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from src.core.config_env import (
    apply_env_overrides as _apply_env_overrides,
)
from src.core.config_env import (
    warn_deprecated_option,
)
from src.core.config_errors import ConfigError
from src.core.config_parsing import (
    coerce_bool as _coerce_bool,
)
from src.core.config_parsing import (
    coerce_float as _coerce_float,
)
from src.core.config_parsing import (
    coerce_int as _coerce_int,
)
from src.core.config_parsing import (
    get_section as _get_section,
)
from src.core.config_parsing import (
    optional_non_empty as _optional_non_empty,
)
from src.core.config_parsing import (
    optional_string as _optional_string,
)
from src.core.config_parsing import (
    require_str as _require_str,
)
from src.core.config_registry import DEPRECATED_BY_YAML


@dataclass
class SmartTubConfig:
    email: str
    password: str | None
    device_id: str | None
    polling_interval_seconds: int = 30
    poll_min_interval_seconds: int = 5  # New: Minimum interval between polls
    state_update_delay_seconds: float = (
        2.5  # Delay after command before fetching updated state
    )
    max_retries: int = 2
    retry_backoff_seconds: int = 5

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SmartTubConfig:
        email = _require_str(data, "email", "smarttub")
        device_id = _optional_string(data.get("device_id"))
        password = _optional_non_empty(data.get("password"))
        if "token" in data:
            raise ConfigError(
                "smarttub.token is not supported; configure smarttub.password instead"
            )
        polling = _coerce_int(
            data.get("polling_interval_seconds"),
            "smarttub.polling_interval_seconds",
            default=30,
            min_value=1,
        )
        poll_min = _coerce_int(
            data.get("poll_min_interval_seconds"),
            "smarttub.poll_min_interval_seconds",
            default=5,
            min_value=1,
        )
        state_update_delay = _coerce_float(
            data.get("state_update_delay_seconds"),
            "smarttub.state_update_delay_seconds",
            default=2.5,
            min_value=0.5,
            max_value=10.0,
        )
        max_retries = _coerce_int(
            data.get("max_retries"), "smarttub.max_retries", default=2, min_value=0
        )
        backoff = _coerce_int(
            data.get("retry_backoff_seconds"),
            "smarttub.retry_backoff_seconds",
            default=5,
            min_value=1,
        )
        return cls(
            email=email,
            password=password,
            device_id=device_id,
            polling_interval_seconds=polling,
            poll_min_interval_seconds=poll_min,
            state_update_delay_seconds=state_update_delay,
            max_retries=max_retries,
            retry_backoff_seconds=backoff,
        )

    def validate(self) -> None:
        if self.polling_interval_seconds <= 0:
            raise ConfigError("smarttub.polling_interval_seconds must be positive")
        if self.poll_min_interval_seconds <= 0:
            raise ConfigError("smarttub.poll_min_interval_seconds must be positive")
        if self.poll_min_interval_seconds > self.polling_interval_seconds:
            raise ConfigError(
                "smarttub.poll_min_interval_seconds cannot be greater than polling_interval_seconds"
            )
        if self.max_retries < 0:
            raise ConfigError("smarttub.max_retries cannot be negative")
        if self.retry_backoff_seconds <= 0:
            raise ConfigError("smarttub.retry_backoff_seconds must be positive")
        if not self.password:
            raise ConfigError("smarttub.password must be provided")


@dataclass
class MQTTTLSConfig:
    enabled: bool = False
    ca_cert_path: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MQTTTLSConfig:
        enabled = _coerce_bool(data.get("enabled"), "mqtt.tls.enabled", default=False)
        ca_cert_path = (
            _optional_string(data.get("ca_cert_path"), allow_empty=True) or ""
        )
        return cls(enabled=enabled, ca_cert_path=ca_cert_path)


@dataclass
class MQTTConfig:
    broker_url: str
    username: str | None = None
    password: str | None = None
    client_id: str = "smarttub-mqtt"
    base_topic: str = "smarttub-mqtt"
    qos: int = 1
    retain: bool = True
    keepalive: int = 60  # New: MQTT keepalive interval
    publish_queue_size: int = 1000
    publish_drain_timeout_seconds: int = 5
    tls: MQTTTLSConfig = field(default_factory=MQTTTLSConfig)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MQTTConfig:
        broker_url = _require_str(data, "broker_url", "mqtt")
        username = _optional_string(data.get("username"))
        password = _optional_string(data.get("password"))
        client_id = (
            _optional_string(data.get("client_id"), allow_empty=False)
            or "smarttub-mqtt"
        )
        base_topic = (
            _optional_string(data.get("base_topic"), allow_empty=False)
            or "smarttub-mqtt"
        )
        qos = _coerce_int(data.get("qos"), "mqtt.qos", default=1, min_value=0)
        if qos > 2:
            raise ConfigError("mqtt.qos must be between 0 and 2")
        retain = _coerce_bool(data.get("retain"), "mqtt.retain", default=True)
        keepalive = _coerce_int(
            data.get("keepalive"), "mqtt.keepalive", default=60, min_value=10
        )
        publish_queue_size = _coerce_int(
            data.get("publish_queue_size"),
            "mqtt.publish_queue_size",
            default=1000,
            min_value=1,
        )
        publish_drain_timeout_seconds = _coerce_int(
            data.get("publish_drain_timeout_seconds"),
            "mqtt.publish_drain_timeout_seconds",
            default=5,
            min_value=1,
        )
        tls_section = cast(
            Mapping[str, Any],
            data.get("tls") if isinstance(data.get("tls"), Mapping) else {},
        )
        tls = MQTTTLSConfig.from_dict(tls_section)
        return cls(
            broker_url=broker_url,
            username=username,
            password=password,
            client_id=client_id,
            base_topic=base_topic,
            qos=qos,
            retain=retain,
            keepalive=keepalive,
            publish_queue_size=publish_queue_size,
            publish_drain_timeout_seconds=publish_drain_timeout_seconds,
            tls=tls,
        )

    def validate(self) -> None:
        if not self.broker_url:
            raise ConfigError("mqtt.broker_url cannot be empty")
        if not self.base_topic:
            raise ConfigError("mqtt.base_topic cannot be empty")
        if not 0 <= self.qos <= 2:
            raise ConfigError("mqtt.qos must be between 0 and 2")
        if self.keepalive < 10:
            raise ConfigError("mqtt.keepalive must be at least 10 seconds")
        if self.publish_queue_size <= 0:
            raise ConfigError("mqtt.publish_queue_size must be positive")
        if self.publish_drain_timeout_seconds <= 0:
            raise ConfigError("mqtt.publish_drain_timeout_seconds must be positive")
        if self.tls.enabled and not self.tls.ca_cert_path:
            raise ConfigError("mqtt.tls.ca_cert_path required when TLS is enabled")


@dataclass
class WebConfig:
    enabled: bool = True  # New: Enable/disable Web UI
    # The documented default is intentionally reachable in the trusted home LAN.
    host: str = "0.0.0.0"  # nosec B104
    port: int = 8080
    auth_enabled: bool = False
    basic_auth_username: str | None = None
    basic_auth_password: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WebConfig:
        enabled = _coerce_bool(data.get("enabled"), "web.enabled", default=True)
        # Keep the same documented trusted-home-network default for partial YAML.
        host = (
            _optional_string(data.get("host"), allow_empty=False) or "0.0.0.0"  # nosec B104
        )
        port = _coerce_int(data.get("port"), "web.port", default=8080, min_value=1)
        auth_enabled = _coerce_bool(
            data.get("auth_enabled"), "web.auth_enabled", default=False
        )
        username = _optional_string(data.get("basic_auth_username"))
        password = _optional_string(data.get("basic_auth_password"))
        return cls(
            enabled=enabled,
            host=host,
            port=port,
            auth_enabled=auth_enabled,
            basic_auth_username=username,
            basic_auth_password=password,
        )

    def validate(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ConfigError("web.port must be between 1 and 65535")
        if self.auth_enabled and (
            not self.basic_auth_username or not self.basic_auth_password
        ):
            raise ConfigError("web basic auth enabled but credentials missing")


@dataclass
class LoggingConfig:
    level: str = "info"
    mqtt_forwarding: bool = False
    stdout_format: str = "json"
    file_path: str | None = None
    # New: Log rotation settings
    log_dir: str = "/var/log/smarttub-mqtt"
    log_max_size_mb: int = 5
    log_max_files: int = 5
    log_compress: bool = True
    mqtt_log_enabled: bool = True
    mqtt_log_level: str = "warning"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LoggingConfig:
        level = (
            _optional_string(data.get("level"), allow_empty=False) or "info"
        ).lower()
        mqtt_forwarding = _coerce_bool(
            data.get("mqtt_forwarding"), "logging.mqtt_forwarding", default=False
        )
        stdout_format = (
            _optional_string(data.get("stdout_format"), allow_empty=False) or "json"
        )
        file_path = _optional_string(data.get("file_path"))
        log_dir = (
            _optional_string(data.get("log_dir"), allow_empty=False)
            or "/var/log/smarttub-mqtt"
        )
        log_max_size_mb = _coerce_int(
            data.get("log_max_size_mb"),
            "logging.log_max_size_mb",
            default=5,
            min_value=1,
        )
        log_max_files = _coerce_int(
            data.get("log_max_files"), "logging.log_max_files", default=5, min_value=1
        )
        log_compress = _coerce_bool(
            data.get("log_compress"), "logging.log_compress", default=True
        )
        mqtt_log_enabled = _coerce_bool(
            data.get("mqtt_log_enabled"), "logging.mqtt_log_enabled", default=True
        )
        mqtt_log_level = (
            _optional_string(data.get("mqtt_log_level"), allow_empty=False) or "warning"
        ).lower()
        return cls(
            level=level,
            mqtt_forwarding=mqtt_forwarding,
            stdout_format=stdout_format,
            file_path=file_path,
            log_dir=log_dir,
            log_max_size_mb=log_max_size_mb,
            log_max_files=log_max_files,
            log_compress=log_compress,
            mqtt_log_enabled=mqtt_log_enabled,
            mqtt_log_level=mqtt_log_level,
        )

    def validate(self) -> None:
        allowed = {"trace", "debug", "info", "warning", "error", "critical"}
        if self.level.lower() not in allowed:
            raise ConfigError(f"logging.level must be one of {sorted(allowed)}")
        if self.mqtt_log_level.lower() not in allowed:
            raise ConfigError(
                f"logging.mqtt_log_level must be one of {sorted(allowed)}"
            )
        if self.log_max_size_mb < 1:
            raise ConfigError("logging.log_max_size_mb must be at least 1 MB")
        if self.log_max_files < 1:
            raise ConfigError("logging.log_max_files must be at least 1")


@dataclass
class WebUIConfig:
    refresh_interval_seconds: int = 5

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WebUIConfig:
        refresh = _coerce_int(
            data.get("refresh_interval_seconds"),
            "web_ui.refresh_interval_seconds",
            default=5,
            min_value=1,
        )
        return cls(refresh_interval_seconds=refresh)

    def validate(self) -> None:
        if self.refresh_interval_seconds <= 0:
            raise ConfigError("web_ui.refresh_interval_seconds must be positive")


@dataclass
class SafetyConfig:
    command_timeout_seconds: int = 7
    command_queue_size: int = 100

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SafetyConfig:
        timeout = _coerce_int(
            data.get("command_timeout_seconds"),
            "safety.command_timeout_seconds",
            default=7,
            min_value=1,
        )
        command_queue_size = _coerce_int(
            data.get("command_queue_size"),
            "safety.command_queue_size",
            default=100,
            min_value=1,
        )
        return cls(
            command_timeout_seconds=timeout,
            command_queue_size=command_queue_size,
        )

    def validate(self) -> None:
        if self.command_timeout_seconds <= 0:
            raise ConfigError("safety.command_timeout_seconds must be positive")
        if self.command_queue_size <= 0:
            raise ConfigError("safety.command_queue_size must be positive")


@dataclass
class CapabilityConfig:
    cache_expiry_seconds: int = 3600  # 1 hour
    refresh_interval_seconds: int = 300  # 5 minutes (changed from 24 hours)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CapabilityConfig:
        cache_expiry = _coerce_int(
            data.get("cache_expiry_seconds"),
            "capability.cache_expiry_seconds",
            default=3600,
            min_value=60,
        )
        refresh_interval = _coerce_int(
            data.get("refresh_interval_seconds"),
            "capability.refresh_interval_seconds",
            default=300,
            min_value=60,
        )
        return cls(
            cache_expiry_seconds=cache_expiry,
            refresh_interval_seconds=refresh_interval,
        )

    def validate(self) -> None:
        if self.cache_expiry_seconds < 60:
            raise ConfigError(
                "capability.cache_expiry_seconds must be at least 60 seconds"
            )
        if self.refresh_interval_seconds < 60:
            raise ConfigError(
                "capability.refresh_interval_seconds must be at least 60 seconds"
            )


@dataclass
class DockerConfig:
    # Use absolute /config by default so containers can mount a host directory
    # to /config. This matches common Docker usage (mount host dir -> /config).
    config_volume: str = "/config"
    env_file: str = "/config/.env"
    healthcheck_interval_seconds: int = 30

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DockerConfig:
        config_volume = (
            _optional_string(data.get("config_volume"), allow_empty=False) or "/config"
        )
        env_file = (
            _optional_string(data.get("env_file"), allow_empty=False) or "/config/.env"
        )
        health = _coerce_int(
            data.get("healthcheck_interval_seconds"),
            "docker.healthcheck_interval_seconds",
            default=30,
            min_value=1,
        )
        return cls(
            config_volume=config_volume,
            env_file=env_file,
            healthcheck_interval_seconds=health,
        )

    def validate(self) -> None:
        if self.healthcheck_interval_seconds <= 0:
            raise ConfigError("docker.healthcheck_interval_seconds must be positive")


@dataclass
class AppConfig:
    smarttub: SmartTubConfig
    mqtt: MQTTConfig
    web: WebConfig
    logging: LoggingConfig
    web_ui: WebUIConfig = field(default_factory=WebUIConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    docker: DockerConfig = field(default_factory=DockerConfig)
    capability: CapabilityConfig = field(default_factory=CapabilityConfig)
    check_smarttub: bool = True  # Default: True, will be read from .env
    discovery_test_all_light_modes: bool = (
        False  # If True: perform exhaustive light mode testing
    )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AppConfig:
        _warn_deprecated_yaml_options(data)
        smarttub = SmartTubConfig.from_dict(_get_section(data, "smarttub"))
        mqtt = MQTTConfig.from_dict(_get_section(data, "mqtt"))
        web = WebConfig.from_dict(_get_section(data, "web"))
        logging = LoggingConfig.from_dict(_get_section(data, "logging"))
        web_ui = WebUIConfig.from_dict(_get_section(data, "web_ui"))
        safety = SafetyConfig.from_dict(_get_section(data, "safety"))
        docker = DockerConfig.from_dict(_get_section(data, "docker"))
        capability = CapabilityConfig.from_dict(_get_section(data, "capability"))
        check_smarttub = True  # Default value: True; may be overridden from .env
        discovery_test_all_light_modes = False  # Default: False
        return cls(
            smarttub=smarttub,
            mqtt=mqtt,
            web=web,
            logging=logging,
            web_ui=web_ui,
            safety=safety,
            docker=docker,
            capability=capability,
            check_smarttub=check_smarttub,
            discovery_test_all_light_modes=discovery_test_all_light_modes,
        )

    def validate(self) -> None:
        from src.core.config_validation import validate_app_config

        validate_app_config(self)


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load configuration from YAML (optional) and .env, apply overrides, and validate."""
    from src.core.config_sources import (
        load_dotenv_from_config_volume,
        read_yaml_mapping,
        resolve_config_path,
    )

    load_dotenv_from_config_volume()
    config_path = resolve_config_path(path)

    # If no YAML config, build config directly from env vars
    if config_path is None:
        # Create empty config structure - will be populated by env overrides
        config = AppConfig(
            smarttub=SmartTubConfig(email="", password=None, device_id=None),
            mqtt=MQTTConfig(broker_url="mqtt://localhost:1883"),
            # Keep the in-memory fallback aligned with the documented LAN default.
            web=WebConfig(
                host="0.0.0.0",  # nosec B104
                port=8080,
            ),
            logging=LoggingConfig(level="info"),
        )
        _apply_env_overrides(config, os.environ)
        config.validate()
        return config

    config = AppConfig.from_dict(read_yaml_mapping(config_path))
    _apply_env_overrides(config, os.environ)
    config.validate()
    return config


def _resolve_config_path(path: Path | str | None) -> Path | None:
    """Compatibility wrapper for the configuration-source boundary."""
    from src.core.config_sources import resolve_config_path

    return resolve_config_path(path)


def _warn_deprecated_yaml_options(data: Mapping[str, Any]) -> None:
    for yaml_path, option in DEPRECATED_BY_YAML.items():
        section_name, key = yaml_path.split(".", maxsplit=1)
        section = data.get(section_name)
        if isinstance(section, Mapping) and key in section:
            warn_deprecated_option(yaml_path, option)
