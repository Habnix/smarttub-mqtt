"""Regression tests for the staged broad-exception reduction policy."""

import re
import tomllib
from pathlib import Path

import pytest

from src.core import config_sources

ROOT = Path(__file__).resolve().parents[1]


def test_ruff_does_not_globally_hide_broad_or_silent_exception_handlers():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    ignored = set(config["tool"].get("ruff", {}).get("lint", {}).get("ignore", []))

    assert "BLE001" not in ignored
    assert "S110" not in ignored


def test_local_broad_exception_suppressions_have_a_monotonic_ceiling():
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "src").rglob("*.py")
    )
    broad_suppressions = re.findall(r"noqa: [^\n]*BLE001", source)
    silent_suppressions = re.findall(r"noqa: [^\n]*S110", source)

    assert len(broad_suppressions) <= 64
    assert len(silent_suppressions) <= 1


def test_dotenv_fallback_handles_filesystem_failure_only(monkeypatch):
    calls: list[object] = []

    def load_dotenv(*, dotenv_path=None):
        calls.append(dotenv_path)
        if dotenv_path is not None:
            raise OSError("mounted configuration unavailable")
        return True

    monkeypatch.setattr(config_sources, "load_dotenv", load_dotenv)

    config_sources.load_dotenv_from_config_volume()

    assert calls == ["/config/.env", None]


def test_dotenv_fallback_does_not_hide_programming_errors(monkeypatch):
    def load_dotenv(*, dotenv_path=None):
        raise TypeError("invalid internal call")

    monkeypatch.setattr(config_sources, "load_dotenv", load_dotenv)

    with pytest.raises(TypeError, match="invalid internal call"):
        config_sources.load_dotenv_from_config_volume()
