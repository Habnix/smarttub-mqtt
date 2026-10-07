"""Regression tests for configuration source precedence and validation."""

from pathlib import Path

import pytest

from src.core.config_env import (
    ENV_OVERRIDES,
    EnvOverride,
    apply_env_overrides,
    render_env_override_reference,
)
from src.core.config_loader import ConfigError, SmartTubConfig, load_config
from src.core.config_registry import (
    CONFIG_OPTIONS,
    DEPRECATED_BY_ENV,
    render_reviewed_configuration_reference,
)

ROOT = Path(__file__).resolve().parents[1]


def _minimal_config():
    from src.core.config_loader import AppConfig, LoggingConfig, MQTTConfig, WebConfig

    return AppConfig(
        smarttub=SmartTubConfig(
            email="schema@example.com", password="password", device_id=None
        ),
        mqtt=MQTTConfig(broker_url="mqtt://broker:1883"),
        web=WebConfig(),
        logging=LoggingConfig(),
    )


def _target_value(config, target):
    value = config
    for part in target.split("."):
        value = getattr(value, part)
    return value


def _valid_schema_value(option: EnvOverride) -> tuple[str, object]:
    if option.parser == "bool":
        return "false", False
    if option.parser == "int":
        value = max(71, int(option.min_value or 0))
        return str(value), value
    if option.parser == "float":
        return "1.5", 1.5
    if option.parser == "lower":
        return "WARNING", "warning"
    if option.parser == "optional_non_empty":
        return "  schema-secret  ", "schema-secret"
    if option.parser == "optional":
        return "  schema-value  ", "schema-value"
    return "  schema-value  ", "schema-value"


def test_environment_overrides_explicit_yaml_configuration(tmp_path, monkeypatch):
    """Environment values override YAML values while other YAML values remain."""
    config_file = tmp_path / "smarttub.yaml"
    config_file.write_text(
        """
smarttub:
  email: yaml@example.com
  password: yaml-password
mqtt:
  broker_url: mqtt://yaml-broker:1883
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("SMARTTUB_EMAIL", "environment@example.com")
    monkeypatch.setenv("MQTT_BROKER_URL", "mqtt://environment-broker:1883")

    config = load_config(config_file)

    assert config.smarttub.email == "environment@example.com"
    assert config.smarttub.password == "yaml-password"
    assert config.mqtt.broker_url == "mqtt://environment-broker:1883"


def test_environment_selects_yaml_configuration(monkeypatch, tmp_path):
    """SMARTTUB_CONFIG selects the YAML file when no CLI path is supplied."""
    config_file = tmp_path / "selected.yaml"
    config_file.write_text(
        """
smarttub:
  email: selected@example.com
  password: selected-password
mqtt:
  broker_url: mqtt://selected-broker:1883
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("SMARTTUB_CONFIG", str(config_file))
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    monkeypatch.delenv("SMARTTUB_EMAIL", raising=False)
    monkeypatch.delenv("SMARTTUB_PASSWORD", raising=False)
    monkeypatch.delenv("MQTT_BROKER_URL", raising=False)

    config = load_config()

    assert config.smarttub.email == "selected@example.com"
    assert config.mqtt.broker_url == "mqtt://selected-broker:1883"


def test_smarttub_token_configuration_is_rejected():
    with pytest.raises(ConfigError, match="smarttub.token is not supported"):
        SmartTubConfig.from_dict(
            {"email": "user@example.com", "password": "password", "token": "token"}
        )


def test_token_only_environment_configuration_is_rejected(monkeypatch):
    monkeypatch.setenv("SMARTTUB_EMAIL", "user@example.com")
    monkeypatch.setenv("MQTT_BROKER_URL", "mqtt://broker:1883")
    monkeypatch.setenv("SMARTTUB_TOKEN", "token")
    monkeypatch.delenv("SMARTTUB_PASSWORD", raising=False)

    with pytest.raises(ConfigError, match="SMARTTUB_TOKEN is not supported"):
        load_config()


def test_queue_limits_are_configurable_from_environment(tmp_path, monkeypatch):
    config_file = tmp_path / "queues.yaml"
    config_file.write_text(
        """
smarttub:
  email: queue@example.com
  password: password
mqtt:
  broker_url: mqtt://broker:1883
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("MQTT_PUBLISH_QUEUE_SIZE", "17")
    monkeypatch.setenv("MQTT_PUBLISH_DRAIN_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("SAFETY_COMMAND_QUEUE_SIZE", "5")

    config = load_config(config_file)

    assert config.mqtt.publish_queue_size == 17
    assert config.mqtt.publish_drain_timeout_seconds == 3
    assert config.safety.command_queue_size == 5


def test_web_ui_refresh_interval_loads_from_environment(tmp_path, monkeypatch):
    config_file = tmp_path / "web-ui.yaml"
    config_file.write_text(
        """
smarttub:
  email: web@example.com
  password: password
mqtt:
  broker_url: mqtt://broker:1883
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("WEB_UI_REFRESH_INTERVAL_SECONDS", "19")

    config = load_config(config_file)

    assert config.web_ui.refresh_interval_seconds == 19


@pytest.mark.parametrize("env_name", sorted(DEPRECATED_BY_ENV))
def test_deprecated_environment_options_warn_and_are_ignored(
    env_name, tmp_path, monkeypatch
):
    config_file = tmp_path / "deprecated-env.yaml"
    config_file.write_text(
        """
smarttub:
  email: deprecated@example.com
  password: password
mqtt:
  broker_url: mqtt://broker:1883
""",
        encoding="utf-8",
    )
    monkeypatch.setenv(env_name, "deliberately-invalid-for-old-validator")

    with pytest.warns(FutureWarning, match=env_name):
        config = load_config(config_file)

    assert not hasattr(config, "observability")
    assert not hasattr(config.safety, "command_max_retries")
    assert not hasattr(config.capability, "enable_auto_discovery")


def test_deprecated_yaml_option_warns_and_is_ignored(tmp_path, monkeypatch):
    config_file = tmp_path / "deprecated-yaml.yaml"
    config_file.write_text(
        """
smarttub:
  email: deprecated@example.com
  password: password
mqtt:
  broker_url: mqtt://broker:1883
safety:
  command_max_retries: invalid-old-value
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("SAFETY_COMMAND_MAX_RETRIES", raising=False)

    with pytest.warns(FutureWarning, match="safety.command_max_retries"):
        config = load_config(config_file)

    assert not hasattr(config.safety, "command_max_retries")


def test_reviewed_configuration_reference_matches_registry():
    reference = ROOT / "docs" / "configuration-reference.md"

    assert reference.read_text(encoding="utf-8") == (
        render_reviewed_configuration_reference()
        + "\n"
        + render_env_override_reference()
    )


def test_env_example_contains_active_reviewed_options_only():
    env_example = (ROOT / "config" / ".env.example").read_text(encoding="utf-8")

    for option in CONFIG_OPTIONS:
        assignment = f"{option.env_name}="
        assert (assignment in env_example) is (option.status == "active")


def test_environment_schema_has_unique_names_and_documented_targets():
    names = [option.env_name for option in ENV_OVERRIDES]

    assert len(names) == len(set(names))
    assert all(
        option.yaml_path
        or option.target in {"check_smarttub", "discovery_test_all_light_modes"}
        for option in ENV_OVERRIDES
    )


@pytest.mark.parametrize("option", ENV_OVERRIDES, ids=lambda option: option.env_name)
def test_each_environment_schema_entry_is_executable(option):
    config = _minimal_config()
    raw, expected = _valid_schema_value(option)

    if option.parser == "unsupported_token":
        with pytest.raises(ConfigError, match="SMARTTUB_TOKEN is not supported"):
            apply_env_overrides(config, {option.env_name: raw})
        return

    apply_env_overrides(config, {option.env_name: raw})

    assert option.target is not None
    assert _target_value(config, option.target) == expected


def test_later_environment_aliases_keep_their_precedence():
    config = _minimal_config()

    apply_env_overrides(
        config,
        {
            "SMARTTUB_POLLING_INTERVAL_SECONDS": "40",
            "POLL_INTERVAL": "41",
            "BASIC_AUTH_USERNAME": "legacy-user",
            "WEB_AUTH_USERNAME": "current-user",
            "CAPABILITY_REFRESH_INTERVAL": "120",
            "CAPABILITY_REFRESH_INTERVAL_SECONDS": "180",
        },
    )

    assert config.smarttub.polling_interval_seconds == 41
    assert config.web.basic_auth_username == "current-user"
    assert config.capability.refresh_interval_seconds == 180


@pytest.mark.parametrize(
    ("env_name", "invalid_value", "message"),
    (
        ("POLL_INTERVAL", "0", "POLL_INTERVAL must be >= 1"),
        ("STATE_UPDATE_DELAY_SECONDS", "0.4", "must be >= 0.5"),
        ("STATE_UPDATE_DELAY_SECONDS", "10.1", "must be <= 10.0"),
        ("CAPABILITY_REFRESH_INTERVAL", "59", "must be >= 60"),
        ("WEB_ENABLED", "sometimes", "must be a boolean value"),
        ("WEB_HOST", " ", "WEB_HOST cannot be empty"),
    ),
)
def test_environment_schema_enforces_declared_parser_boundaries(
    env_name, invalid_value, message
):
    with pytest.raises(ConfigError, match=message):
        apply_env_overrides(_minimal_config(), {env_name: invalid_value})
