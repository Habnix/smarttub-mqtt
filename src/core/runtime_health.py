"""Safe liveness and readiness reporting for the application runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.core.config_loader import AppConfig


class RuntimeHealth:
    """Evaluate dependencies without exposing credentials or raw exceptions."""

    def __init__(
        self,
        config: AppConfig,
        state_manager: Any,
        *,
        mqtt_broker: Any = None,
        smarttub_client: Any = None,
        command_manager: Any = None,
    ) -> None:
        self.config = config
        self.state_manager = state_manager
        self.mqtt_broker = mqtt_broker
        self.smarttub_client = smarttub_client
        self.command_manager = command_manager

    @staticmethod
    def liveness(now: datetime | None = None) -> dict[str, Any]:
        """Report only that the HTTP process can execute application code."""
        observed = now or datetime.now(UTC)
        return {"status": "live", "timestamp": observed.isoformat()}

    def readiness(self, now: datetime | None = None) -> dict[str, Any]:
        """Report whether all configured runtime dependencies are usable."""
        observed = now or datetime.now(UTC)
        mqtt = self._mqtt_status()
        worker = self._command_worker_status()
        smarttub, state = self._smarttub_status(observed)
        components = {
            "mqtt": mqtt,
            "smarttub": smarttub,
            "state": state,
            "command_worker": worker,
        }
        ready = all(
            component["status"] in {"ready", "disabled"}
            for component in components.values()
        )
        return {
            "status": "ready" if ready else "not_ready",
            "timestamp": observed.isoformat(),
            "components": components,
        }

    def _mqtt_status(self) -> dict[str, Any]:
        connected = bool(getattr(self.mqtt_broker, "is_connected", False))
        return {
            "status": "ready" if connected else "not_ready",
            "connected": connected,
        }

    def _command_worker_status(self) -> dict[str, Any]:
        running = bool(getattr(self.command_manager, "is_worker_running", False))
        return {
            "status": "ready" if running else "not_ready",
            "running": running,
        }

    def _smarttub_status(self, now: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
        if not getattr(self.config, "check_smarttub", True):
            return {"status": "disabled"}, {"status": "disabled"}

        connected = bool(getattr(self.smarttub_client, "is_connected", False))
        smarttub = {
            "status": "ready" if connected else "not_ready",
            "connected": connected,
        }
        return smarttub, self._state_status(now)

    def _state_status(self, now: datetime) -> dict[str, Any]:
        snapshot = self.state_manager.get_latest_snapshot()
        max_age = self._max_snapshot_age_seconds()
        if not isinstance(snapshot, dict):
            return {
                "status": "not_ready",
                "quality": "unavailable",
                "age_seconds": None,
                "max_age_seconds": max_age,
            }

        quality_data = snapshot.get("quality", {})
        quality = (
            quality_data.get("status", "unavailable")
            if isinstance(quality_data, dict)
            else "unavailable"
        )
        age = self._snapshot_age_seconds(snapshot, now)
        ready = quality == "live" and age is not None and age <= max_age
        return {
            "status": "ready" if ready else "not_ready",
            "quality": quality,
            "age_seconds": age,
            "max_age_seconds": max_age,
        }

    def _max_snapshot_age_seconds(self) -> int:
        polling = getattr(
            getattr(self.config, "smarttub", None), "polling_interval_seconds", 30
        )
        return max(120, int(polling) * 3)

    @staticmethod
    def _snapshot_age_seconds(snapshot: dict[str, Any], now: datetime) -> int | None:
        quality = snapshot.get("quality", {})
        timestamp = (
            quality.get("observed_at") if isinstance(quality, dict) else None
        ) or snapshot.get("timestamp")
        if not isinstance(timestamp, str):
            return None
        try:
            observed = datetime.fromisoformat(timestamp)
        except ValueError:
            return None
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        return max(0, int((now - observed).total_seconds()))
