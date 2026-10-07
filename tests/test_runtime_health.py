from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from src.core.runtime_health import RuntimeHealth


class _StateManager:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def get_latest_snapshot(self):
        return self.snapshot


def _config(*, check_smarttub=True):
    return SimpleNamespace(
        check_smarttub=check_smarttub,
        smarttub=SimpleNamespace(polling_interval_seconds=30),
    )


def _health(snapshot, *, mqtt=True, smarttub=True, worker=True, check=True):
    return RuntimeHealth(
        _config(check_smarttub=check),
        _StateManager(snapshot),
        mqtt_broker=SimpleNamespace(is_connected=mqtt),
        smarttub_client=SimpleNamespace(is_connected=smarttub),
        command_manager=SimpleNamespace(is_worker_running=worker),
    )


def _live_snapshot(observed_at):
    timestamp = observed_at.isoformat()
    return {
        "timestamp": timestamp,
        "quality": {"status": "live", "observed_at": timestamp},
        "components": {},
    }


def test_readiness_requires_all_configured_dependencies():
    now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)

    report = _health(_live_snapshot(now - timedelta(seconds=30))).readiness(now)

    assert report["status"] == "ready"
    assert all(
        component["status"] == "ready" for component in report["components"].values()
    )


def test_readiness_reports_each_degraded_dependency_without_internal_errors():
    now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    stale = _live_snapshot(now - timedelta(seconds=121))

    report = _health(stale, mqtt=False, smarttub=False, worker=False).readiness(now)

    assert report["status"] == "not_ready"
    assert report["components"]["mqtt"] == {
        "status": "not_ready",
        "connected": False,
    }
    assert report["components"]["smarttub"]["status"] == "not_ready"
    assert report["components"]["state"]["status"] == "not_ready"
    assert report["components"]["state"]["age_seconds"] == 121
    assert report["components"]["command_worker"]["status"] == "not_ready"
    assert "error" not in str(report).lower()


def test_disabled_smarttub_polling_is_not_a_readiness_failure():
    report = _health(None, check=False).readiness(
        datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    )

    assert report["status"] == "ready"
    assert report["components"]["smarttub"] == {"status": "disabled"}
    assert report["components"]["state"] == {"status": "disabled"}


def test_liveness_does_not_include_dependency_state():
    report = RuntimeHealth.liveness(datetime(2026, 8, 22, 12, 0, tzinfo=UTC))

    assert report == {"status": "live", "timestamp": "2026-08-22T12:00:00+00:00"}
