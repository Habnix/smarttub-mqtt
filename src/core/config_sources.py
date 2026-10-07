"""Read configuration source files without knowing the application schema."""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.core.config_errors import ConfigError


def load_dotenv_from_config_volume() -> None:
    """Load the mounted dotenv file, falling back to dotenv's default lookup."""
    try:
        load_dotenv(dotenv_path=str(Path("/config") / ".env"))
    except OSError:
        load_dotenv()


def resolve_config_path(
    path: Path | str | None, env: Mapping[str, str] | None = None
) -> Path | None:
    """Resolve an explicit or environment-provided YAML configuration path."""
    environment = os.environ if env is None else env
    if path is not None:
        candidate = Path(path)
    else:
        env_path = environment.get("SMARTTUB_CONFIG") or environment.get("CONFIG_FILE")
        if not env_path:
            return None
        candidate = Path(env_path)

    if not candidate.exists():
        raise FileNotFoundError(candidate)
    if not candidate.is_file():
        raise ConfigError(f"Configuration path {candidate} is not a file")
    return candidate


def read_yaml_mapping(config_path: Path) -> MutableMapping[str, Any]:
    """Read one YAML mapping and translate parse errors to ``ConfigError``."""
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - defensive branch
        raise ConfigError(f"Failed to parse configuration file: {exc}") from exc

    if not isinstance(raw, MutableMapping):
        raise ConfigError("Configuration root must be a mapping")
    return raw
