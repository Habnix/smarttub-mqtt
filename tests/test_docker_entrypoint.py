"""Regression tests for Docker environment validation."""

from pathlib import Path

import pytest

from src.docker.entrypoint import EntrypointError, validate_environment


def test_entrypoint_rejects_unsupported_smarttub_token(monkeypatch):
    monkeypatch.setenv("SMARTTUB_EMAIL", "user@example.com")
    monkeypatch.setenv("MQTT_BROKER_URL", "mqtt://broker:1883")
    monkeypatch.setenv("SMARTTUB_TOKEN", "token")
    monkeypatch.delenv("SMARTTUB_PASSWORD", raising=False)

    with pytest.raises(EntrypointError, match="SMARTTUB_TOKEN is not supported"):
        validate_environment()


def test_entrypoint_default_log_directory_matches_compose_mount(monkeypatch):
    monkeypatch.setenv("SMARTTUB_EMAIL", "user@example.com")
    monkeypatch.setenv("SMARTTUB_PASSWORD", "password")
    monkeypatch.setenv("MQTT_BROKER_URL", "mqtt://broker:1883")
    monkeypatch.delenv("SMARTTUB_TOKEN", raising=False)
    monkeypatch.delenv("LOG_DIR", raising=False)

    assert validate_environment()["LOG_DIR"] == "/logs"


def test_docker_image_and_compose_mount_use_the_same_log_directory():
    project_root = Path(__file__).resolve().parents[1]
    dockerfile = (project_root / "Dockerfile").read_text(encoding="utf-8")
    compose_file = (project_root / "docker-compose.yml").read_text(encoding="utf-8")

    assert 'VOLUME ["/config", "/logs"]' in dockerfile
    assert "LOG_DIR=/logs" in dockerfile
    assert "- ./logs:/logs" in compose_file
