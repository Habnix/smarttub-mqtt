"""Regression tests for HTTP Basic authentication in the Web UI."""

from fastapi.testclient import TestClient

from src.core.config_loader import (
    AppConfig,
    LoggingConfig,
    MQTTConfig,
    SmartTubConfig,
    WebConfig,
)
from src.web.app import create_app


class _StateManager:
    _last_snapshot = None

    def get_latest_snapshot(self):
        return self._last_snapshot

    @staticmethod
    def get_safe_fallback_state():
        return {"timestamp": "2026-01-01T00:00:00+00:00", "components": {}}


def _client() -> TestClient:
    config = AppConfig(
        smarttub=SmartTubConfig(
            email="spa@example.com", password="secret", device_id=None
        ),
        mqtt=MQTTConfig(broker_url="mqtt://broker"),
        web=WebConfig(
            auth_enabled=True, basic_auth_username="admin", basic_auth_password="secret"
        ),
        logging=LoggingConfig(),
    )
    return TestClient(
        create_app(config, _StateManager()), raise_server_exceptions=False
    )


def test_protected_endpoint_without_credentials_returns_basic_auth_challenge():
    response = _client().get("/api/state")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"
    assert response.json() == {"detail": "Authentication required"}


def test_protected_endpoint_with_invalid_credentials_returns_401():
    response = _client().get("/api/state", auth=("admin", "wrong"))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"
    assert response.json() == {"detail": "Invalid credentials"}


def test_malformed_basic_credentials_are_rejected_without_internal_error():
    response = _client().get(
        "/api/state", headers={"Authorization": "Basic !!!not-base64!!!"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_health_endpoint_remains_available_without_credentials():
    response = _client().get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_liveness_and_readiness_remain_available_without_credentials():
    client = _client()

    assert client.get("/live").status_code == 200
    readiness = client.get("/ready")
    assert readiness.status_code == 503
    assert readiness.json()["status"] == "not_ready"


def test_protected_endpoint_with_valid_credentials_is_available():
    response = _client().get("/api/state", auth=("admin", "secret"))

    assert response.status_code == 200
