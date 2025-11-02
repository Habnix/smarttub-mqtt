from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, MutableMapping

import yaml
from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when configuration parsing or validation fails."""


@dataclass
class SmartTubConfig:
    email: str
    password: str | None
    device_id: str | None
    token: str | None
    polling_interval_seconds: int = 30
    poll_min_interval_seconds: int = 5  # New: Minimum interval between polls
    state_update_delay_seconds: float = 2.5  # Delay after command before fetching updated state
    max_retries: int = 2
    retry_backoff_seconds: int = 5

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SmartTubConfig":
        email = _require_str(data, "email", "smarttub")
        device_id = _optional_string(data.get("device_id"))
        password = _optional_non_empty(data.get("password"))
        token = _optional_non_empty(data.get("token"))
        polling = _coerce_int(data.get("polling_interval_seconds"), "smarttub.polling_interval_seconds", default=30, min_value=1)
        poll_min = _coerce_int(data.get("poll_min_interval_seconds"), "smarttub.poll_min_interval_seconds", default=5, min_value=1)
        state_update_delay = _coerce_float(data.get("state_update_delay_seconds"), "smarttub.state_update_delay_seconds", default=2.5, min_value=0.5, max_value=10.0)
        max_retries = _coerce_int(data.get("max_retries"), "smarttub.max_retries", default=2, min_value=0)
        backoff = _coerce_int(data.get("retry_backoff_seconds"), "smarttub.retry_backoff_seconds", default=5, min_value=1)
        return cls(
            email=email,
            password=password,
            device_id=device_id,
            token=token,
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
            raise ConfigError("smarttub.poll_min_interval_seconds cannot be greater than polling_interval_seconds")
        if self.max_retries < 0:
            raise ConfigError("smarttub.max_retries cannot be negative")
        if self.retry_backoff_seconds <= 0:
            raise ConfigError("smarttub.retry_backoff_seconds must be positive")
        if not self.password and not self.token:
            raise ConfigError("smarttub.password or smarttub.token must be provided")


@dataclass
class MQTTTLSConfig:
    enabled: bool = False
    ca_cert_path: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MQTTTLSConfig":
        enabled = _coerce_bool(data.get("enabled"), "mqtt.tls.enabled", default=False)
        ca_cert_path = _optional_string(data.get("ca_cert_path"), allow_empty=True) or ""
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
    tls: MQTTTLSConfig = field(default_factory=MQTTTLSConfig)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MQTTConfig":
        broker_url = _require_str(data, "broker_url", "mqtt")
        username = _optional_string(data.get("username"))
        password = _optional_string(data.get("password"))
        client_id = _optional_string(data.get("client_id"), allow_empty=False) or "smarttub-mqtt"
        base_topic = _optional_string(data.get("base_topic"), allow_empty=False) or "smarttub-mqtt"
        qos = _coerce_int(data.get("qos"), "mqtt.qos", default=1, min_value=0)
        if qos > 2:
            raise ConfigError("mqtt.qos must be between 0 and 2")
        retain = _coerce_bool(data.get("retain"), "mqtt.retain", default=True)
        keepalive = _coerce_int(data.get("keepalive"), "mqtt.keepalive", default=60, min_value=10)
        tls_section = data.get("tls") if isinstance(data.get("tls"), Mapping) else {}
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
        if self.tls.enabled and not self.tls.ca_cert_path:
            raise ConfigError("mqtt.tls.ca_cert_path required when TLS is enabled")


@dataclass
class WebConfig:
    enabled: bool = True  # New: Enable/disable Web UI
    host: str = "0.0.0.0"
    port: int = 8080
    auth_enabled: bool = False
    basic_auth_username: str | None = None
    basic_auth_password: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebConfig":
        enabled = _coerce_bool(data.get("enabled"), "web.enabled", default=True)
        host = _optional_string(data.get("host"), allow_empty=False) or "0.0.0.0"
        port = _coerce_int(data.get("port"), "web.port", default=8080, min_value=1)
        auth_enabled = _coerce_bool(data.get("auth_enabled"), "web.auth_enabled", default=False)
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
        if self.auth_enabled and (not self.basic_auth_username or not self.basic_auth_password):
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
    def from_dict(cls, data: Mapping[str, Any]) -> "LoggingConfig":
        level = (_optional_string(data.get("level"), allow_empty=False) or "info").lower()
        mqtt_forwarding = _coerce_bool(data.get("mqtt_forwarding"), "logging.mqtt_forwarding", default=False)
        stdout_format = _optional_string(data.get("stdout_format"), allow_empty=False) or "json"
        file_path = _optional_string(data.get("file_path"))
        log_dir = _optional_string(data.get("log_dir"), allow_empty=False) or "/var/log/smarttub-mqtt"
        log_max_size_mb = _coerce_int(data.get("log_max_size_mb"), "logging.log_max_size_mb", default=5, min_value=1)
        log_max_files = _coerce_int(data.get("log_max_files"), "logging.log_max_files", default=5, min_value=1)
        log_compress = _coerce_bool(data.get("log_compress"), "logging.log_compress", default=True)
        mqtt_log_enabled = _coerce_bool(data.get("mqtt_log_enabled"), "logging.mqtt_log_enabled", default=True)
        mqtt_log_level = (_optional_string(data.get("mqtt_log_level"), allow_empty=False) or "warning").lower()
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
            mqtt_log_level=mqtt_log_level
        )

    def validate(self) -> None:
        allowed = {"trace", "debug", "info", "warning", "error", "critical"}
        if self.level.lower() not in allowed:
            raise ConfigError(f"logging.level must be one of {sorted(allowed)}")
        if self.mqtt_log_level.lower() not in allowed:
            raise ConfigError(f"logging.mqtt_log_level must be one of {sorted(allowed)}")
        if self.log_max_size_mb < 1:
            raise ConfigError("logging.log_max_size_mb must be at least 1 MB")
        if self.log_max_files < 1:
            raise ConfigError("logging.log_max_files must be at least 1")


@dataclass
class ObservabilityConfig:
    heartbeat_interval_seconds: int = 30
    telemetry_batch_size: int = 10

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ObservabilityConfig":
        heartbeat = _coerce_int(data.get("heartbeat_interval_seconds"), "observability.heartbeat_interval_seconds", default=30, min_value=1)
        batch = _coerce_int(data.get("telemetry_batch_size"), "observability.telemetry_batch_size", default=10, min_value=1)
        return cls(heartbeat_interval_seconds=heartbeat, telemetry_batch_size=batch)

    def validate(self) -> None:
        if self.heartbeat_interval_seconds <= 0:
            raise ConfigError("observability.heartbeat_interval_seconds must be positive")
        if self.telemetry_batch_size <= 0:
            raise ConfigError("observability.telemetry_batch_size must be positive")


@dataclass
class WebUIConfig:
    refresh_interval_seconds: int = 5

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebUIConfig":
        refresh = _coerce_int(data.get("refresh_interval_seconds"), "web_ui.refresh_interval_seconds", default=5, min_value=1)
        return cls(refresh_interval_seconds=refresh)

    def validate(self) -> None:
        if self.refresh_interval_seconds <= 0:
            raise ConfigError("web_ui.refresh_interval_seconds must be positive")


@dataclass
class SafetyConfig:
    fail_safe_mode: str = "stop_pumps"
    command_timeout_seconds: int = 7
    post_command_wait_seconds: int = 12
    command_verification_retries: int = 3
    command_max_retries: int = 2  # New: Maximum retries for failed commands

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SafetyConfig":
        fail_safe_mode = _optional_string(data.get("fail_safe_mode"), allow_empty=False) or "stop_pumps"
        timeout = _coerce_int(data.get("command_timeout_seconds"), "safety.command_timeout_seconds", default=7, min_value=1)
        post_wait = _coerce_int(data.get("post_command_wait_seconds"), "safety.post_command_wait_seconds", default=12, min_value=1)
        retries = _coerce_int(data.get("command_verification_retries"), "safety.command_verification_retries", default=3, min_value=0)
        max_retries = _coerce_int(data.get("command_max_retries"), "safety.command_max_retries", default=2, min_value=0)
        return cls(
            fail_safe_mode=fail_safe_mode,
            command_timeout_seconds=timeout,
            post_command_wait_seconds=post_wait,
            command_verification_retries=retries,
            command_max_retries=max_retries,
        )

    def validate(self) -> None:
        if not self.fail_safe_mode:
            raise ConfigError("safety.fail_safe_mode cannot be empty")
        if self.command_timeout_seconds <= 0:
            raise ConfigError("safety.command_timeout_seconds must be positive")
        if self.post_command_wait_seconds <= 0:
            raise ConfigError("safety.post_command_wait_seconds must be positive")
        if self.command_verification_retries < 0:
            raise ConfigError("safety.command_verification_retries cannot be negative")
        if self.command_max_retries < 0:
            raise ConfigError("safety.command_max_retries cannot be negative")


@dataclass
class CapabilityConfig:
    cache_expiry_seconds: int = 3600  # 1 hour
    refresh_interval_seconds: int = 300  # 5 minutes (changed from 24 hours)
    discovery_refresh_interval: int = 3600  # New: Full discovery refresh (1 hour)
    enable_auto_discovery: bool = True

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CapabilityConfig":
        cache_expiry = _coerce_int(data.get("cache_expiry_seconds"), "capability.cache_expiry_seconds", default=3600, min_value=60)
        refresh_interval = _coerce_int(data.get("refresh_interval_seconds"), "capability.refresh_interval_seconds", default=300, min_value=60)
        discovery_refresh = _coerce_int(data.get("discovery_refresh_interval"), "capability.discovery_refresh_interval", default=3600, min_value=300)
        auto_discovery = _coerce_bool(data.get("enable_auto_discovery"), "capability.enable_auto_discovery", default=True)
        return cls(
            cache_expiry_seconds=cache_expiry,
            refresh_interval_seconds=refresh_interval,
            discovery_refresh_interval=discovery_refresh,
            enable_auto_discovery=auto_discovery,
        )

    def validate(self) -> None:
        if self.cache_expiry_seconds < 60:
            raise ConfigError("capability.cache_expiry_seconds must be at least 60 seconds")
        if self.refresh_interval_seconds < 60:
            raise ConfigError("capability.refresh_interval_seconds must be at least 60 seconds")
        if self.discovery_refresh_interval < 300:
            raise ConfigError("capability.discovery_refresh_interval must be at least 300 seconds (5 minutes)")


@dataclass
class DockerConfig:
    # Use absolute /config by default so containers can mount a host directory
    # to /config. This matches common Docker usage (mount host dir -> /config).
    config_volume: str = "/config"
    env_file: str = "/config/.env"
    healthcheck_interval_seconds: int = 30

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DockerConfig":
        config_volume = _optional_string(data.get("config_volume"), allow_empty=False) or "/config"
        env_file = _optional_string(data.get("env_file"), allow_empty=False) or "/config/.env"
        health = _coerce_int(data.get("healthcheck_interval_seconds"), "docker.healthcheck_interval_seconds", default=30, min_value=1)
        return cls(config_volume=config_volume, env_file=env_file, healthcheck_interval_seconds=health)

    def validate(self) -> None:
        if self.healthcheck_interval_seconds <= 0:
            raise ConfigError("docker.healthcheck_interval_seconds must be positive")


@dataclass
class AppConfig:
    smarttub: SmartTubConfig
    mqtt: MQTTConfig
    web: WebConfig
    logging: LoggingConfig
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    web_ui: WebUIConfig = field(default_factory=WebUIConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    docker: DockerConfig = field(default_factory=DockerConfig)
    capability: CapabilityConfig = field(default_factory=CapabilityConfig)
    check_smarttub: bool = True  # Default: True, will be read from .env
    discovery_test_all_light_modes: bool = False  # If True: perform exhaustive light mode testing

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AppConfig":
        smarttub = SmartTubConfig.from_dict(_get_section(data, "smarttub"))
        mqtt = MQTTConfig.from_dict(_get_section(data, "mqtt"))
        web = WebConfig.from_dict(_get_section(data, "web"))
        logging = LoggingConfig.from_dict(_get_section(data, "logging"))
        observability = ObservabilityConfig.from_dict(_get_section(data, "observability"))
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
            observability=observability,
            web_ui=web_ui,
            safety=safety,
            docker=docker,
            capability=capability,
            check_smarttub=check_smarttub,
            discovery_test_all_light_modes=discovery_test_all_light_modes,
        )

    def validate(self) -> None:
        self.smarttub.validate()
        self.mqtt.validate()
        self.web.validate()
        self.logging.validate()
        self.observability.validate()
        self.web_ui.validate()
        self.safety.validate()
        self.docker.validate()
        self.capability.validate()


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load configuration from YAML, apply environment overrides, and validate."""

    # Load environment overrides from ./config/.env by default so the config
    # directory can be mounted into Docker. This ensures secrets (passwords,
    # tokens) are read from ./config/.env when present.
    try:
        # Prefer absolute /config so containers can mount a host directory to /config
        dotenv_path = Path("/config") / ".env"
        load_dotenv(dotenv_path=str(dotenv_path))
    except Exception:
        # Fallback to default behaviour if anything goes wrong
        load_dotenv()
    config_path = _resolve_config_path(path)

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - defensive branch
        raise ConfigError(f"Failed to parse configuration file: {exc}") from exc

    if not isinstance(raw, MutableMapping):
        raise ConfigError("Configuration root must be a mapping")

    config = AppConfig.from_dict(raw)
    _apply_env_overrides(config, os.environ)
    config.validate()
    return config


def _resolve_config_path(path: Path | str | None) -> Path:
    if path is not None:
        candidate = Path(path)
    else:
        env_path = os.environ.get("SMARTTUB_CONFIG") or os.environ.get("CONFIG_FILE")
        # Default to absolute /config/smarttub.yaml so Docker mounts to /config work
        candidate = Path(env_path) if env_path else Path("/config") / "smarttub.yaml"

    if not candidate.exists():
        raise FileNotFoundError(candidate)
    if not candidate.is_file():
        raise ConfigError(f"Configuration path {candidate} is not a file")
    return candidate


def _apply_env_overrides(config: AppConfig, env: Mapping[str, str]) -> None:
    if "SMARTTUB_EMAIL" in env:
        value = env["SMARTTUB_EMAIL"].strip()
        if not value:
            raise ConfigError("SMARTTUB_EMAIL cannot be empty")
        config.smarttub.email = value
    # Read CHECK_SMARTTUB from .env
    if "CHECK_SMARTTUB" in env:
        config.check_smarttub = _coerce_bool(env.get("CHECK_SMARTTUB"), "CHECK_SMARTTUB")
    # Read DISCOVERY_TEST_ALL_LIGHT_MODES from .env
    if "DISCOVERY_TEST_ALL_LIGHT_MODES" in env:
        config.discovery_test_all_light_modes = _coerce_bool(env.get("DISCOVERY_TEST_ALL_LIGHT_MODES"), "DISCOVERY_TEST_ALL_LIGHT_MODES")
    if "SMARTTUB_PASSWORD" in env:
        config.smarttub.password = _optional_non_empty(env.get("SMARTTUB_PASSWORD"))
    if "SMARTTUB_TOKEN" in env:
        config.smarttub.token = _optional_non_empty(env.get("SMARTTUB_TOKEN"))
    if "SMARTTUB_DEVICE_ID" in env:
        value = env["SMARTTUB_DEVICE_ID"].strip()
        if value:  # Only set if non-empty (auto-detected otherwise)
            config.smarttub.device_id = value
    if "SMARTTUB_POLLING_INTERVAL_SECONDS" in env:
        config.smarttub.polling_interval_seconds = _coerce_int(
            env.get("SMARTTUB_POLLING_INTERVAL_SECONDS"),
            "SMARTTUB_POLLING_INTERVAL_SECONDS",
            min_value=1,
        )
    if "SMARTTUB_MAX_RETRIES" in env:
        config.smarttub.max_retries = _coerce_int(env.get("SMARTTUB_MAX_RETRIES"), "SMARTTUB_MAX_RETRIES", min_value=0)
    if "SMARTTUB_RETRY_BACKOFF_SECONDS" in env:
        config.smarttub.retry_backoff_seconds = _coerce_int(
            env.get("SMARTTUB_RETRY_BACKOFF_SECONDS"),
            "SMARTTUB_RETRY_BACKOFF_SECONDS",
            min_value=1,
        )
    if "POLL_INTERVAL" in env:
        config.smarttub.polling_interval_seconds = _coerce_int(
            env.get("POLL_INTERVAL"),
            "POLL_INTERVAL",
            min_value=1,
        )
    if "POLL_MIN_INTERVAL" in env:
        config.smarttub.poll_min_interval_seconds = _coerce_int(
            env.get("POLL_MIN_INTERVAL"),
            "POLL_MIN_INTERVAL",
            min_value=1,
        )
    if "STATE_UPDATE_DELAY_SECONDS" in env:
        config.smarttub.state_update_delay_seconds = _coerce_float(
            env.get("STATE_UPDATE_DELAY_SECONDS"),
            "STATE_UPDATE_DELAY_SECONDS",
            min_value=0.5,
            max_value=10.0,
        )

    if "MQTT_BROKER_URL" in env:
        value = env["MQTT_BROKER_URL"].strip()
        if not value:
            raise ConfigError("MQTT_BROKER_URL cannot be empty")
        config.mqtt.broker_url = value
    if "MQTT_USERNAME" in env:
        config.mqtt.username = _optional_string(env.get("MQTT_USERNAME"))
    if "MQTT_PASSWORD" in env:
        config.mqtt.password = _optional_string(env.get("MQTT_PASSWORD"))
    if "MQTT_CLIENT_ID" in env:
        value = env["MQTT_CLIENT_ID"].strip()
        if value:  # Only set if non-empty
            config.mqtt.client_id = value
    if "MQTT_BASE_TOPIC" in env:
        value = env["MQTT_BASE_TOPIC"].strip()
        if not value:
            raise ConfigError("MQTT_BASE_TOPIC cannot be empty")
        config.mqtt.base_topic = value
    if "MQTT_QOS" in env:
        config.mqtt.qos = _coerce_int(env.get("MQTT_QOS"), "MQTT_QOS", min_value=0)
    if "MQTT_RETAIN" in env:
        config.mqtt.retain = _coerce_bool(env.get("MQTT_RETAIN"), "MQTT_RETAIN")
    if "MQTT_KEEPALIVE" in env:
        config.mqtt.keepalive = _coerce_int(env.get("MQTT_KEEPALIVE"), "MQTT_KEEPALIVE", min_value=10)

    if "LOG_LEVEL" in env:
        value = env["LOG_LEVEL"].strip()
        if not value:
            raise ConfigError("LOG_LEVEL cannot be empty")
        config.logging.level = value.lower()
    if "LOG_MQTT_FORWARDING" in env:
        config.logging.mqtt_forwarding = _coerce_bool(env.get("LOG_MQTT_FORWARDING"), "LOG_MQTT_FORWARDING")
    if "LOG_STDOUT_FORMAT" in env:
        value = env["LOG_STDOUT_FORMAT"].strip()
        if not value:
            raise ConfigError("LOG_STDOUT_FORMAT cannot be empty")
        config.logging.stdout_format = value
    if "LOG_FILE_PATH" in env:
        config.logging.file_path = _optional_string(env.get("LOG_FILE_PATH"))
    if "LOG_DIR" in env:
        config.logging.log_dir = env.get("LOG_DIR", "/var/log/smarttub-mqtt").strip()
    if "LOG_MAX_SIZE_MB" in env:
        config.logging.log_max_size_mb = _coerce_int(env.get("LOG_MAX_SIZE_MB"), "LOG_MAX_SIZE_MB", min_value=1)
    if "LOG_MAX_FILES" in env:
        config.logging.log_max_files = _coerce_int(env.get("LOG_MAX_FILES"), "LOG_MAX_FILES", min_value=1)
    if "LOG_COMPRESS" in env:
        config.logging.log_compress = _coerce_bool(env.get("LOG_COMPRESS"), "LOG_COMPRESS")
    if "LOG_MQTT_ENABLED" in env:
        config.logging.mqtt_log_enabled = _coerce_bool(env.get("LOG_MQTT_ENABLED"), "LOG_MQTT_ENABLED")
    if "LOG_MQTT_LEVEL" in env:
        config.logging.mqtt_log_level = env.get("LOG_MQTT_LEVEL", "warning").strip().lower()

    if "WEB_HOST" in env:
        value = env["WEB_HOST"].strip()
        if not value:
            raise ConfigError("WEB_HOST cannot be empty")
        config.web.host = value
    if "WEB_ENABLED" in env:
        config.web.enabled = _coerce_bool(env.get("WEB_ENABLED"), "WEB_ENABLED")
    if "WEB_PORT" in env:
        config.web.port = _coerce_int(env.get("WEB_PORT"), "WEB_PORT", min_value=1)
    if "WEB_AUTH_ENABLED" in env:
        config.web.auth_enabled = _coerce_bool(env.get("WEB_AUTH_ENABLED"), "WEB_AUTH_ENABLED")
    if "BASIC_AUTH_USERNAME" in env:
        config.web.basic_auth_username = _optional_string(env.get("BASIC_AUTH_USERNAME"))
    if "WEB_AUTH_USERNAME" in env:
        config.web.basic_auth_username = _optional_string(env.get("WEB_AUTH_USERNAME"))
    if "BASIC_AUTH_PASSWORD" in env:
        config.web.basic_auth_password = _optional_string(env.get("BASIC_AUTH_PASSWORD"))
    if "WEB_AUTH_PASSWORD" in env:
        config.web.basic_auth_password = _optional_string(env.get("WEB_AUTH_PASSWORD"))

    if "WEB_UI_REFRESH_INTERVAL_SECONDS" in env:
        config.web_ui.refresh_interval_seconds = _coerce_int(
            env.get("WEB_UI_REFRESH_INTERVAL_SECONDS"),
            "WEB_UI_REFRESH_INTERVAL_SECONDS",
            min_value=1,
        )

    if "OBS_HEARTBEAT_INTERVAL_SECONDS" in env:
        config.observability.heartbeat_interval_seconds = _coerce_int(
            env.get("OBS_HEARTBEAT_INTERVAL_SECONDS"),
            "OBS_HEARTBEAT_INTERVAL_SECONDS",
            min_value=1,
        )
    if "OBS_TELEMETRY_BATCH_SIZE" in env:
        config.observability.telemetry_batch_size = _coerce_int(
            env.get("OBS_TELEMETRY_BATCH_SIZE"),
            "OBS_TELEMETRY_BATCH_SIZE",
            min_value=1,
        )

    if "SAFETY_FAIL_SAFE_MODE" in env:
        value = env["SAFETY_FAIL_SAFE_MODE"].strip()
        if not value:
            raise ConfigError("SAFETY_FAIL_SAFE_MODE cannot be empty")
        config.safety.fail_safe_mode = value
    if "SAFETY_COMMAND_TIMEOUT_SECONDS" in env:
        config.safety.command_timeout_seconds = _coerce_int(
            env.get("SAFETY_COMMAND_TIMEOUT_SECONDS"),
            "SAFETY_COMMAND_TIMEOUT_SECONDS",
            min_value=1,
        )
    if "SAFETY_POST_COMMAND_WAIT_SECONDS" in env:
        config.safety.post_command_wait_seconds = _coerce_int(
            env.get("SAFETY_POST_COMMAND_WAIT_SECONDS"),
            "SAFETY_POST_COMMAND_WAIT_SECONDS",
            min_value=1,
        )
    if "SAFETY_COMMAND_VERIFICATION_RETRIES" in env:
        config.safety.command_verification_retries = _coerce_int(
            env.get("SAFETY_COMMAND_VERIFICATION_RETRIES"),
            "SAFETY_COMMAND_VERIFICATION_RETRIES",
            min_value=0,
        )
    if "SAFETY_COMMAND_MAX_RETRIES" in env:
        config.safety.command_max_retries = _coerce_int(
            env.get("SAFETY_COMMAND_MAX_RETRIES"),
            "SAFETY_COMMAND_MAX_RETRIES",
            min_value=0,
        )

    if "DOCKER_CONFIG_VOLUME" in env:
        value = env["DOCKER_CONFIG_VOLUME"].strip()
        if not value:
            raise ConfigError("DOCKER_CONFIG_VOLUME cannot be empty")
        config.docker.config_volume = value
    if "DOCKER_ENV_FILE" in env:
        value = env["DOCKER_ENV_FILE"].strip()
        if not value:
            raise ConfigError("DOCKER_ENV_FILE cannot be empty")
        config.docker.env_file = value
    if "DOCKER_HEALTHCHECK_INTERVAL_SECONDS" in env:
        config.docker.healthcheck_interval_seconds = _coerce_int(
            env.get("DOCKER_HEALTHCHECK_INTERVAL_SECONDS"),
            "DOCKER_HEALTHCHECK_INTERVAL_SECONDS",
            min_value=1,
        )

    if "CAPABILITY_CACHE_EXPIRY_SECONDS" in env:
        config.capability.cache_expiry_seconds = _coerce_int(
            env.get("CAPABILITY_CACHE_EXPIRY_SECONDS"),
            "CAPABILITY_CACHE_EXPIRY_SECONDS",
            min_value=60,
        )
    if "CAPABILITY_REFRESH_INTERVAL" in env:
        config.capability.refresh_interval_seconds = _coerce_int(
            env.get("CAPABILITY_REFRESH_INTERVAL"),
            "CAPABILITY_REFRESH_INTERVAL",
            min_value=60,
        )
    if "CAPABILITY_REFRESH_INTERVAL_SECONDS" in env:
        config.capability.refresh_interval_seconds = _coerce_int(
            env.get("CAPABILITY_REFRESH_INTERVAL_SECONDS"),
            "CAPABILITY_REFRESH_INTERVAL_SECONDS",
            min_value=60,
        )
    if "DISCOVERY_REFRESH_INTERVAL" in env:
        config.capability.discovery_refresh_interval = _coerce_int(
            env.get("DISCOVERY_REFRESH_INTERVAL"),
            "DISCOVERY_REFRESH_INTERVAL",
            min_value=300,
        )
    if "CAPABILITY_ENABLE_AUTO_DISCOVERY" in env:
        config.capability.enable_auto_discovery = _coerce_bool(
            env.get("CAPABILITY_ENABLE_AUTO_DISCOVERY"),
            "CAPABILITY_ENABLE_AUTO_DISCOVERY",
        )


def _get_section(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    section = data.get(key, {})
    if section is None:
        return {}
    if not isinstance(section, Mapping):
        raise ConfigError(f"{key} section must be a mapping")
    return section


def _require_str(data: Mapping[str, Any], key: str, namespace: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{namespace}.{key} is required")
    return value.strip()


def _optional_non_empty(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"Expected string or null, received {type(value).__name__}")
    trimmed = value.strip()
    return trimmed or None


def _optional_string(value: Any, *, allow_empty: bool = True) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed and not allow_empty:
            return None
        return trimmed if trimmed or allow_empty else None
    raise ConfigError(f"Expected string or null, received {type(value).__name__}")


def _coerce_int(value: Any, field_name: str, *, default: int | None = None, min_value: int | None = None) -> int:
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


def _coerce_float(value: Any, field_name: str, *, default: float | None = None, min_value: float | None = None, max_value: float | None = None) -> float:
    """Coerce value to float with validation."""
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


def _coerce_bool(value: Any, field_name: str, *, default: bool | None = None) -> bool:
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