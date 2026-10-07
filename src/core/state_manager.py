from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import UTC, datetime

from src.core.smarttub_client import SmartTubClient
from src.core.state_models import StateQualityStatus, StateSnapshot
from src.core.state_publisher import StatePublisher
from src.mqtt.topic_mapper import MQTTTopicMapper

logger = logging.getLogger("smarttub.core")


class StateManager:
    """Own the latest observation and publish one full snapshot per poll."""

    PUBLICATION_MODE = "full_snapshot"

    def __init__(self, smarttub_client: SmartTubClient, topic_mapper: MQTTTopicMapper):
        self.smarttub_client = smarttub_client
        self.topic_mapper = topic_mapper
        self._publisher = StatePublisher(topic_mapper)
        self._last_snapshot: StateSnapshot | None = None
        self._quality: StateQualityStatus = "unavailable"
        self._last_success_at: str | None = None
        self._lock = threading.Lock()
        self._observers: list[Callable[[StateSnapshot], Awaitable[None]]] = []

    def subscribe(self, callback: Callable[[StateSnapshot], Awaitable[None]]) -> None:
        """Subscribe to complete state observations for local consumers."""
        if callback not in self._observers:
            self._observers.append(callback)

    async def _notify_observers(self, snapshot: StateSnapshot) -> None:
        if self._observers:
            await asyncio.gather(
                *(callback(deepcopy(snapshot)) for callback in self._observers),
                return_exceptions=True,
            )

    async def sync_state(self) -> bool:
        """Synchronize and publish the complete current state to MQTT.

        Full retained component topics are deliberate: there is no competing
        delta state or partial-merge model in this service.
        """
        try:
            snapshot = await self.smarttub_client.get_state_snapshot()
            observed_at = snapshot.get("timestamp") or datetime.now(UTC).isoformat()
            snapshot["timestamp"] = observed_at
            snapshot["quality"] = {
                "status": "live",
                "observed_at": observed_at,
                "last_success_at": observed_at,
                "checked_at": datetime.now(UTC).isoformat(),
            }

            # Publish full state every poll cycle (user requested). This keeps
            # per-pump subtopics (state/type/speed/last_updated) up-to-date even
            # when values didn't change. It increases MQTT traffic but makes
            # UIs and integrations consistent.
            message_count = self._publisher.publish(snapshot)

            # The Web API reads this snapshot under the same lock. Keeping the
            # write synchronized ensures readers never observe a replacement
            # while creating their isolated deep copy.
            with self._lock:
                self._last_snapshot = snapshot
                self._quality = "live"
                self._last_success_at = observed_at
            self._publish_quality("live", observed_at)
            await self._notify_observers(snapshot)
            logger.debug(
                f"Published {message_count} state messages to MQTT (full publish per poll)"
            )
            return True

        except Exception:
            logger.exception("State sync failed")
            await self._handle_sync_error()
            return False

    async def _handle_sync_error(self) -> None:
        """Mark observations stale/unavailable without publishing fake values."""
        with self._lock:
            self._quality = (
                "stale" if self._last_snapshot is not None else "unavailable"
            )
            if self._last_snapshot is not None:
                observed_at = self._last_snapshot.get("timestamp")
                self._last_snapshot["quality"] = {
                    "status": self._quality,
                    "observed_at": observed_at,
                    "last_success_at": self._last_success_at,
                    "checked_at": datetime.now(UTC).isoformat(),
                }
            else:
                observed_at = None
            quality = self._quality
        self._publish_quality(quality, observed_at)
        await self._notify_observers(
            self.get_latest_snapshot() or self.get_safe_fallback_state()
        )
        logger.info("Marked SmartTub state as %s after sync error", quality)

    def _publish_quality(
        self, status: StateQualityStatus, observed_at: str | None
    ) -> None:
        """Publish availability independently from retained component telemetry."""
        try:
            spa_id = self._last_snapshot.get("spa_id") if self._last_snapshot else None
            messages = self.topic_mapper.publish_state_quality(
                spa_id=spa_id,
                status=status,
                observed_at=observed_at,
                last_success_at=self._last_success_at,
                checked_at=datetime.now(UTC).isoformat(),
            )
            self.topic_mapper.publish_messages(messages)
        except Exception:
            logger.exception("Failed to publish SmartTub state quality")

    def get_safe_fallback_state(self) -> StateSnapshot:
        """Return an unavailable envelope without synthetic telemetry."""
        timestamp = datetime.now(UTC).isoformat()
        return {
            "timestamp": timestamp,
            "quality": {
                "status": "unavailable",
                "observed_at": None,
                "last_success_at": self._last_success_at,
                "checked_at": timestamp,
            },
            "components": {},
        }

    def get_latest_snapshot(self) -> StateSnapshot | None:
        """Return an isolated copy of the most recently synchronized state.

        Consumers such as the web layer must not read or mutate the internal
        snapshot directly. A deep copy keeps this read API safe for nested
        pump and light data while preserving the snapshot's public shape.
        """
        with self._lock:
            if self._last_snapshot is None:
                return None
            return deepcopy(self._last_snapshot)
