"""Contracts for the single application version and public project metadata."""

import importlib.metadata
import tomllib
from pathlib import Path

import pytest

from src.cli.run import _parse_args
from src.core.config_loader import (
    AppConfig,
    LoggingConfig,
    MQTTConfig,
    SmartTubConfig,
    WebConfig,
)
from src.core.version import __version__, get_smarttub_mqtt_version
from src.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_package_metadata_comes_from_the_canonical_source() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["dynamic"] == ["version"]
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"] == (
        "src.core.version.__version__"
    )
    assert pyproject["project"]["scripts"]["smarttub-mqtt"] == "src.cli.run:main"
    assert get_smarttub_mqtt_version() == __version__
    assert importlib.metadata.version("smarttub-mqtt") == __version__


def test_cli_version_uses_the_same_value(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _parse_args(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"smarttub-mqtt {__version__}\n"


def test_project_urls_point_to_the_canonical_repository() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    urls = pyproject["project"]["urls"]
    repository = "https://github.com/Habnix/smarttub-mqtt"

    assert urls["Homepage"] == repository
    assert urls["Source"] == repository
    assert urls["Issues"] == f"{repository}/issues"


def test_fastapi_openapi_uses_the_canonical_version() -> None:
    config = AppConfig(
        smarttub=SmartTubConfig(
            email="spa@example.com", password="secret", device_id=None
        ),
        mqtt=MQTTConfig(broker_url="mqtt://broker"),
        web=WebConfig(),
        logging=LoggingConfig(),
    )

    class _StateManager:
        _last_snapshot = None

        def get_latest_snapshot(self):
            return self._last_snapshot

        @staticmethod
        def get_safe_fallback_state():
            return {"timestamp": "2026-01-01T00:00:00+00:00", "components": {}}

    app = create_app(config, _StateManager())

    assert app.openapi()["info"]["version"] == __version__


def test_oci_version_is_injected_from_ci_instead_of_duplicated() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "ARG APP_VERSION" in dockerfile
    assert 'LABEL org.opencontainers.image.version="${APP_VERSION}"' in dockerfile
    assert "APP_VERSION=${{ steps.version.outputs.value }}" in workflow
