"""Output adapters for legacy full-device discovery results."""

from __future__ import annotations

import asyncio
import json
import logging
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.config_loader import AppConfig
from src.core.discovery_repository import DiscoveryRepository, default_discovery_path
from src.mqtt.topic_mapper import MQTTMessage, publish_state_snapshot

logger = logging.getLogger(__name__)


class DiscoveryPersistenceError(RuntimeError):
    """Discovery results could not be serialized or persisted."""


class DiscoveryFileRepository:
    """Write compact and diagnostic discovery YAML without mutating input."""

    COMPACT_KEYS = (
        "spa_id",
        "discovered_at",
        "capabilities",
        "spa",
        "heater",
        "pumps",
        "lights",
    )
    RAW_KEYS = (
        "status_full",
        "debug_status",
        "capabilities_python-smarttub",
        "errors",
        "reminders",
        "energy_usage",
    )

    def __init__(
        self,
        primary_dir: Path | None = None,
        fallback_dir: Path | None = None,
    ) -> None:
        self.primary_dir = primary_dir or default_discovery_path().parent
        self.fallback_dir = fallback_dir

    def save(self, discovery_results: dict[str, Any]) -> tuple[Path, Path]:
        """Persist both files, falling back to the project config directory."""
        compact, raw = self.build_documents(discovery_results)

        try:
            return self._write(self.primary_dir, compact, raw)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Could not write discovery data to %s: %s", self.primary_dir, exc
            )
            primary_error = exc

        if self.fallback_dir is None:
            raise DiscoveryPersistenceError(
                f"Could not persist discovery results to {self.primary_dir}"
            ) from primary_error
        try:
            return self._write(self.fallback_dir, compact, raw)
        except Exception as fallback_error:
            raise DiscoveryPersistenceError(
                "Could not persist discovery results to either "
                f"{self.primary_dir} or {self.fallback_dir}"
            ) from fallback_error

    async def save_async(self, discovery_results: dict[str, Any]) -> tuple[Path, Path]:
        return await asyncio.to_thread(self.save, discovery_results)

    def build_documents(
        self, discovery_results: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Build compact and diagnostic documents from independent copies."""
        compact_results: dict[str, Any] = {}
        raw_results: dict[str, Any] = {}

        for spa_id, source in discovery_results.items():
            result = deepcopy(source)
            compact = {key: result[key] for key in self.COMPACT_KEYS if key in result}
            raw = {key: result[key] for key in self.RAW_KEYS if key in result}
            raw.update(
                {
                    key: value
                    for key, value in result.items()
                    if key not in self.COMPACT_KEYS and key not in self.RAW_KEYS
                }
            )
            self._compact_spa(compact)
            self._compact_write_topics(compact)
            compact_results[spa_id] = compact
            raw_results[spa_id] = raw

        return (
            {"discovered_items": compact_results},
            {"discovered_items": raw_results},
        )

    @staticmethod
    def _compact_spa(compact: dict[str, Any]) -> None:
        spa = compact.get("spa")
        if not isinstance(spa, dict):
            return
        essential = {key: spa[key] for key in ("name", "model") if key in spa}
        if essential:
            compact["spa"] = essential
        else:
            compact.pop("spa", None)

    @staticmethod
    def _compact_write_topics(compact: dict[str, Any]) -> None:
        for component in ("pumps", "lights"):
            items = compact.get(component)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                topic = item.get("state_writetopic")
                if not isinstance(topic, str):
                    continue
                parts = topic.split("/")
                if len(parts) >= 4 and parts[-3] == component:
                    item["state_writetopic"] = "/".join(parts[-3:])

    @staticmethod
    def _write(
        directory: Path,
        compact: dict[str, Any],
        raw: dict[str, Any],
    ) -> tuple[Path, Path]:
        compact_path = directory / "discovered_items.yaml"
        raw_path = directory / "spa_raw_data.yaml"
        DiscoveryRepository(compact_path).write(compact)
        DiscoveryRepository(raw_path).write(raw)
        logger.info("Wrote discovered items to %s", compact_path)
        logger.info("Wrote raw discovery data to %s", raw_path)
        return compact_path, raw_path


class DiscoveryMqttPublisher:
    """Publish full discovery results and derived pump metadata."""

    def __init__(self, config: AppConfig, topic_mapper: Any) -> None:
        self.config = config
        self.topic_mapper = topic_mapper

    def publish_pump_metadata(self, results: dict[str, Any]) -> None:
        messages: list[MQTTMessage] = []
        for spa_id, payload in results.items():
            pumps = payload.get("pumps", [])
            if not isinstance(pumps, list):
                continue
            snapshot = self._pump_snapshot(spa_id, payload, pumps)
            self._publish(self._map_snapshot(snapshot))
            messages.extend(self._pump_meta_messages(spa_id, payload, pumps))
        self._publish(messages)

    def publish_results(self, results: dict[str, Any]) -> None:
        messages = [
            MQTTMessage(
                topic=(f"{self.config.mqtt.base_topic}/{spa_id}/discovery/result"),
                payload=json.dumps(payload),
                qos=1,
                retain=True,
            )
            for spa_id, payload in results.items()
        ]
        for spa_id, message in zip(results, messages, strict=True):
            logger.info(
                "publishing-discovery-result",
                extra={"topic": message.topic, "retain": True, "spa_id": spa_id},
            )
        self._publish(messages)

    def publish_status(self, spa_id: str, status: str) -> None:
        self._publish(
            [
                MQTTMessage(
                    topic=(f"{self.config.mqtt.base_topic}/{spa_id}/discovery/status"),
                    payload=status,
                    qos=1,
                    retain=True,
                )
            ]
        )

    def publish_progress(
        self,
        spa_id: str,
        *,
        current: int,
        total: int,
        detail: str,
    ) -> None:
        base = f"{self.config.mqtt.base_topic}/{spa_id}/discovery"
        self._publish(
            [
                MQTTMessage(
                    topic=f"{base}/progress",
                    payload=f"{current}/{total}",
                    qos=1,
                    retain=False,
                ),
                MQTTMessage(
                    topic=f"{base}/detail",
                    payload=detail,
                    qos=1,
                    retain=False,
                ),
            ]
        )

    def _map_snapshot(self, snapshot: dict[str, Any]) -> list[MQTTMessage]:
        if hasattr(self.topic_mapper, "publish_state_snapshot"):
            return self.topic_mapper.publish_state_snapshot(snapshot)
        return publish_state_snapshot(self.config, snapshot)

    def _publish(self, messages: list[MQTTMessage]) -> None:
        if not messages:
            return
        if hasattr(self.topic_mapper, "publish_messages"):
            self.topic_mapper.publish_messages(messages)
            return
        mqtt_client = getattr(self.topic_mapper, "mqtt_client", None)
        if mqtt_client is None:
            return
        for message in messages:
            mqtt_client.publish_sync(
                topic=message.topic,
                payload=message.payload,
                qos=message.qos,
                retain=message.retain,
            )

    def _pump_snapshot(
        self, spa_id: str, payload: dict[str, Any], pumps: list[Any]
    ) -> dict[str, Any]:
        normalized = []
        for pump in pumps:
            if not isinstance(pump, dict):
                continue
            raw_value = pump.get("raw")
            raw: dict[str, Any] = raw_value if isinstance(raw_value, dict) else {}
            properties_value = raw.get("properties")
            properties: dict[str, Any] = (
                properties_value if isinstance(properties_value, dict) else {}
            )
            normalized.append(
                {
                    "id": self._first_scalar(pump.get("id")) or "unknown",
                    "type": self._first_scalar(
                        pump.get("type"), properties.get("type"), raw.get("type")
                    ),
                    "state": self._first_scalar(
                        properties.get("state"), raw.get("state"), pump.get("state")
                    )
                    or "unknown",
                    "speed": self._first_scalar(
                        properties.get("speed"), raw.get("speed"), pump.get("speed")
                    ),
                }
            )
        return {
            "timestamp": payload.get("discovered_at") or datetime.now(UTC).isoformat(),
            "spa_id": spa_id,
            "components": {"pumps": normalized},
        }

    def _pump_meta_messages(
        self, spa_id: str, payload: dict[str, Any], pumps: list[Any]
    ) -> list[MQTTMessage]:
        messages = []
        base = self.config.mqtt.base_topic
        for pump in pumps:
            if not isinstance(pump, dict):
                continue
            pump_id = self._first_scalar(pump.get("id")) or "unknown"
            raw_value = pump.get("raw")
            raw: dict[str, Any] = raw_value if isinstance(raw_value, dict) else {}
            properties_value = raw.get("properties")
            properties: dict[str, Any] = (
                properties_value if isinstance(properties_value, dict) else {}
            )
            meta = {
                "id": pump_id,
                "type": self._first_scalar(properties.get("type"), pump.get("type")),
                "supports": pump.get("supports", {}),
                "state_writetopic": (
                    f"{base}/{spa_id}/pumps/{pump_id}/state_writetopic"
                ),
                "discovered_at": payload.get("discovered_at"),
            }
            topic = f"{base}/{spa_id}/pumps/{pump_id}/meta"
            messages.append(
                MQTTMessage(topic=topic, payload=json.dumps(meta), qos=1, retain=True)
            )
            logger.info(
                "created-pump-meta-discovery",
                extra={"topic": topic, "spa_id": spa_id, "pump_id": pump_id},
            )
        return messages

    @staticmethod
    def _first_scalar(*values: Any) -> Any | None:
        for value in values:
            if value is None or isinstance(value, (dict, list)) and not value:
                continue
            return value
        return None
