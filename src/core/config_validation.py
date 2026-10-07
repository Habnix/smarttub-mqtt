"""Cross-section validation for the assembled application configuration."""

from __future__ import annotations

from typing import Any


def validate_app_config(config: Any) -> None:
    """Validate all configuration sections after sources and overrides merge."""
    config.smarttub.validate()
    config.mqtt.validate()
    config.web.validate()
    config.logging.validate()
    config.web_ui.validate()
    config.safety.validate()
    config.docker.validate()
    config.capability.validate()
