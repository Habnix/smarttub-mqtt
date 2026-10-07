from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

from src.core.config_loader import AppConfig
from src.core.discovery_repository import DiscoveryRepository
from src.mqtt.message import MQTTMessage
from src.mqtt.publisher import MqttPublisher
from src.mqtt.topic_encoders import (
    DiscoveryTopicEncoder,
    MetadataTopicEncoder,
    detected_light_modes,
)

logger = logging.getLogger("smarttub.mqtt.mapper")


DetectedModesLookup = Callable[[str, str], list[str]]


class StateTopicEncoder:
    """Purely encode SmartTub state snapshots into MQTT messages."""

    def __init__(
        self,
        config: AppConfig,
        detected_modes_lookup: DetectedModesLookup | None = None,
    ) -> None:
        self.config = config
        self._detected_modes_lookup = detected_modes_lookup or (
            lambda _spa_id, _light_id: []
        )

    def _base_topic(self, spa_id: Any = None) -> str:
        """Return the configured topic root, scoped to one spa when known."""
        resolved_spa_id = spa_id or getattr(self.config.smarttub, "device_id", None)
        if resolved_spa_id:
            return f"{self.config.mqtt.base_topic}/{resolved_spa_id}"
        return self.config.mqtt.base_topic

    def publish_state_snapshot(self, snapshot: Mapping[str, Any]) -> list[MQTTMessage]:
        """Convert a SmartTub state snapshot into MQTT messages."""
        spa_id = snapshot.get("spa_id") or getattr(
            self.config.smarttub, "device_id", None
        )
        base_topic = self._base_topic(spa_id)
        timestamp = snapshot.get("timestamp", "")
        components = snapshot.get("components", {})

        logger.debug(f"Publishing snapshot with components: {list(components.keys())}")
        if "pumps" in components:
            pumps_list = components.get("pumps")
            logger.debug(
                f"Pumps in snapshot: {len(pumps_list) if isinstance(pumps_list, list) else 'NOT A LIST'} items"
            )
        if "lights" in components:
            lights_list = components.get("lights")
            logger.debug(
                f"Lights in snapshot: {len(lights_list) if isinstance(lights_list, list) else 'NOT A LIST'} items"
            )

        messages: list[MQTTMessage] = []
        messages.extend(
            self._map_heater(components.get("heater"), base_topic, timestamp, spa_id)
        )
        messages.extend(
            self._map_filtration(components.get("filtration"), base_topic, timestamp)
        )
        messages.extend(self._map_spa(components.get("spa"), base_topic, timestamp))
        messages.extend(
            self._map_pumps(components.get("pumps"), base_topic, timestamp, spa_id)
        )
        messages.extend(
            self._map_lights(components.get("lights"), base_topic, timestamp, spa_id)
        )
        return messages

    def publish_state_quality(
        self,
        *,
        spa_id: str | None,
        status: str,
        observed_at: str | None,
        last_success_at: str | None,
        checked_at: str,
    ) -> list[MQTTMessage]:
        """Build retained availability and observation-quality messages."""
        base_topic = self._base_topic(spa_id)
        availability = "online" if status == "live" else "offline"
        quality = {
            "status": status,
            "observed_at": observed_at,
            "last_success_at": last_success_at,
            "checked_at": checked_at,
        }
        return [
            MQTTMessage(
                topic=f"{base_topic}/availability",
                payload=availability,
                qos=1,
                retain=True,
            ),
            MQTTMessage(
                topic=f"{base_topic}/state/quality",
                payload=json.dumps(quality),
                qos=1,
                retain=True,
            ),
        ]

    def _map_heater(
        self,
        heater: Any,
        base_topic: str,
        timestamp: str,
        spa_id: Any,
    ) -> list[MQTTMessage]:
        messages: list[MQTTMessage] = []
        # Heater: simple state and temperature topics, plus one last_updated topic
        # Following T052: Separate read topics (current API values) from write topics
        if isinstance(heater, dict):
            # state as plain string (read-only, current API value)
            messages.append(
                MQTTMessage(
                    topic=f"{base_topic}/heater/state",
                    payload=str(heater.get("state", "unknown")),
                    qos=1,
                    retain=True,
                )
            )
            # temperature as plain numeric or string (read-only, current API value)
            if heater.get("temperature") is not None:
                messages.append(
                    MQTTMessage(
                        topic=f"{base_topic}/heater/temperature",
                        payload=str(heater.get("temperature")),
                        qos=1,
                        retain=True,
                    )
                )
            # target_temperature: current API value (read)
            if heater.get("target_temperature") is not None:
                messages.append(
                    MQTTMessage(
                        topic=f"{base_topic}/heater/target_temperature",
                        payload=str(heater.get("target_temperature")),
                        qos=1,
                        retain=True,
                    )
                )
            # mode: current API value (read)
            if heater.get("mode") is not None:
                messages.append(
                    MQTTMessage(
                        topic=f"{base_topic}/heater/mode",
                        payload=str(heater.get("mode")),
                        qos=1,
                        retain=True,
                    )
                )
            # single top-level timestamp for heater
            messages.append(
                MQTTMessage(
                    topic=f"{base_topic}/heater/last_updated",
                    payload=str(timestamp),
                    qos=1,
                    retain=True,
                )
            )

            # T052: Publish heater meta topic documenting write topics for OpenHAB
            # These document where OpenHAB should write commands
            try:
                meta = {
                    "supports": {
                        "target_temperature": heater.get("target_temperature")
                        is not None,
                        "mode": heater.get("mode") is not None,
                    },
                    # T052: publish the recommended command topics for heater
                    "target_temperature_writetopic": f"{base_topic}/heater/target_temperature_writetopic",
                    "mode_writetopic": f"{base_topic}/heater/mode_writetopic",
                    "last_updated": timestamp,
                }
                topic_meta = f"{base_topic}/heater/meta"
                messages.append(
                    MQTTMessage(
                        topic=topic_meta, payload=json.dumps(meta), qos=1, retain=True
                    )
                )
                logger.info(
                    "created-heater-meta", extra={"topic": topic_meta, "spa_id": spa_id}
                )
            except Exception:
                # don't let a meta serialization error break snapshot publish
                logger.debug(
                    "Could not serialize optional heater metadata", exc_info=True
                )
        return messages

    def _map_filtration(
        self, filtration: Any, base_topic: str, timestamp: str
    ) -> list[MQTTMessage]:
        messages: list[MQTTMessage] = []
        # Primary filtration: ECO_MODE is independent of the heater's ECONOMY mode.
        if isinstance(filtration, dict):
            for field in ("mode", "cycle", "duration", "start_hour", "status"):
                if filtration.get(field) is not None:
                    messages.append(
                        MQTTMessage(
                            topic=f"{base_topic}/filtration/{field}",
                            payload=str(filtration.get(field)),
                            qos=1,
                            retain=True,
                        )
                    )
            messages.append(
                MQTTMessage(
                    topic=f"{base_topic}/filtration/last_updated",
                    payload=str(timestamp),
                    qos=1,
                    retain=True,
                )
            )
            topic_meta = f"{base_topic}/filtration/meta"
            meta = {
                "supports": {"mode": filtration.get("mode") is not None},
                "supported_modes": filtration.get(
                    "supported_modes", ["NORMAL", "NANO_MODE", "ECO_MODE"]
                ),
                "mode_writetopic": f"{base_topic}/filtration/mode_writetopic",
                "last_updated": timestamp,
            }
            messages.append(
                MQTTMessage(
                    topic=topic_meta,
                    payload=json.dumps(meta),
                    qos=1,
                    retain=True,
                )
            )
        return messages

    def _map_spa(self, spa: Any, base_topic: str, timestamp: str) -> list[MQTTMessage]:
        messages: list[MQTTMessage] = []
        # Spa: overall state and temperature readings + one last_updated
        if isinstance(spa, dict):
            messages.append(
                MQTTMessage(
                    topic=f"{base_topic}/spa/state",
                    payload=str(spa.get("state", "unknown")),
                    qos=1,
                    retain=True,
                )
            )
            if spa.get("water_temperature") is not None:
                messages.append(
                    MQTTMessage(
                        topic=f"{base_topic}/spa/water_temperature",
                        payload=str(spa.get("water_temperature")),
                        qos=1,
                        retain=True,
                    )
                )
            if spa.get("air_temperature") is not None:
                messages.append(
                    MQTTMessage(
                        topic=f"{base_topic}/spa/air_temperature",
                        payload=str(spa.get("air_temperature")),
                        qos=1,
                        retain=True,
                    )
                )
            messages.append(
                MQTTMessage(
                    topic=f"{base_topic}/spa/last_updated",
                    payload=str(timestamp),
                    qos=1,
                    retain=True,
                )
            )
        return messages

    def _map_pumps(
        self,
        pumps: Any,
        base_topic: str,
        timestamp: str,
        spa_id: Any,
    ) -> list[MQTTMessage]:
        messages: list[MQTTMessage] = []
        # Pumps: publish aggregated list (already done) and per-pump simple topics; one pumps/last_updated
        if isinstance(pumps, list):
            for pump in pumps:
                pid = pump.get("id") or pump.get("pumpId") or "unknown"
                # state -> plain
                messages.append(
                    MQTTMessage(
                        topic=f"{base_topic}/pumps/{pid}/state",
                        payload=str(pump.get("state", "unknown")),
                        qos=1,
                        retain=True,
                    )
                )
                # id and type as separate simple topics for easy discovery
                messages.append(
                    MQTTMessage(
                        topic=f"{base_topic}/pumps/{pid}/id",
                        payload=str(pid),
                        qos=1,
                        retain=True,
                    )
                )
                messages.append(
                    MQTTMessage(
                        topic=f"{base_topic}/pumps/{pid}/type",
                        payload=str(pump.get("type", "unknown")),
                        qos=1,
                        retain=True,
                    )
                )
                # speed -> plain
                if pump.get("speed") is not None:
                    messages.append(
                        MQTTMessage(
                            topic=f"{base_topic}/pumps/{pid}/speed",
                            payload=str(pump.get("speed")),
                            qos=1,
                            retain=True,
                        )
                    )
                if pump.get("speed_capability") is not None:
                    messages.append(
                        MQTTMessage(
                            topic=f"{base_topic}/pumps/{pid}/speed_capability",
                            payload=str(pump.get("speed_capability")),
                            qos=1,
                            retain=True,
                        )
                    )
                # last_updated per pump
                messages.append(
                    MQTTMessage(
                        topic=f"{base_topic}/pumps/{pid}/last_updated",
                        payload=str(timestamp),
                        qos=1,
                        retain=True,
                    )
                )
                # per-pump retained meta topic describing the pump and where to
                # send commands for it. This includes a state_writetopic so MQTT
                # clients can discover the proper control topic for the pump.
                # T052: Using _writetopic convention instead of set_ prefix
                try:
                    meta = {
                        "id": pid,
                        "type": pump.get("type"),
                        "supports": {
                            "speed": bool(pump.get("supported_speeds")),
                        },
                        "speed_capability": pump.get("speed_capability", "unknown"),
                        "supported_speeds": pump.get("supported_speeds", []),
                        # T052: publish the recommended command topic for this pump
                        "state_writetopic": f"{base_topic}/pumps/{pid}/state_writetopic",
                        "last_updated": timestamp,
                    }
                    topic_meta = f"{base_topic}/pumps/{pid}/meta"
                    messages.append(
                        MQTTMessage(
                            topic=topic_meta,
                            payload=json.dumps(meta),
                            qos=1,
                            retain=True,
                        )
                    )
                    # Info-level log so operators can see meta topics even when
                    # logger is set to INFO (debug logs are more verbose).
                    logger.info(
                        "created-pump-meta",
                        extra={"topic": topic_meta, "spa_id": spa_id, "pump_id": pid},
                    )
                except Exception:
                    # don't let a meta serialization error break snapshot publish
                    logger.debug(
                        "Could not serialize optional pump metadata", exc_info=True
                    )
            # pumps top-level timestamp
            messages.append(
                MQTTMessage(
                    topic=f"{base_topic}/pumps/last_updated",
                    payload=str(timestamp),
                    qos=1,
                    retain=True,
                )
            )

            # No legacy (non-spa) per-pump topics are published anymore; prefer
            # spa-scoped topics under <base_topic>/<spa_id>/pumps/...
        return messages

    def _map_lights(
        self,
        lights: Any,
        base_topic: str,
        timestamp: str,
        spa_id: Any,
    ) -> list[MQTTMessage]:
        messages: list[MQTTMessage] = []
        # Lights: per-zone topics for state, color and brightness; single lights/last_updated
        # T052: Publish read topics (current API values) and document write topics in meta
        # T053: Include mode for special light modes (LowSpeedWheel, ColorWheel, etc.)
        if isinstance(lights, list):
            for light in lights:
                lid = light.get("id") or f"zone_{light.get('zone', 'unknown')}"
                # Read topic: current state from API (on/off)
                messages.append(
                    MQTTMessage(
                        topic=f"{base_topic}/lights/{lid}/state",
                        payload=str(light.get("state", "unknown")),
                        qos=1,
                        retain=True,
                    )
                )
                # Read topic: current mode from API (OFF, WHITE, PURPLE, LowSpeedWheel, ColorWheel, etc.)
                if light.get("mode") is not None:
                    messages.append(
                        MQTTMessage(
                            topic=f"{base_topic}/lights/{lid}/mode",
                            payload=str(light.get("mode")),
                            qos=1,
                            retain=True,
                        )
                    )
                # Read topic: current color from API
                if light.get("color") is not None:
                    messages.append(
                        MQTTMessage(
                            topic=f"{base_topic}/lights/{lid}/color",
                            payload=str(light.get("color")),
                            qos=1,
                            retain=True,
                        )
                    )
                # Read topic: current brightness from API
                if light.get("brightness") is not None:
                    messages.append(
                        MQTTMessage(
                            topic=f"{base_topic}/lights/{lid}/brightness",
                            payload=str(light.get("brightness")),
                            qos=1,
                            retain=True,
                        )
                    )
                # cycleSpeed was added by python-smarttub 0.0.48. It is a
                # read-only status value; the upstream API has no setter.
                if light.get("cycle_speed") is not None:
                    messages.append(
                        MQTTMessage(
                            topic=f"{base_topic}/lights/{lid}/cycle_speed",
                            payload=str(light.get("cycle_speed")),
                            qos=1,
                            retain=True,
                        )
                    )
                # Per-light timestamp
                messages.append(
                    MQTTMessage(
                        topic=f"{base_topic}/lights/{lid}/last_updated",
                        payload=str(timestamp),
                        qos=1,
                        retain=True,
                    )
                )

                # T052: per-light meta topic documenting write topics for OpenHAB
                try:
                    # Load detected_modes from YAML if available
                    detected_modes = self._detected_modes_lookup(str(spa_id), str(lid))

                    meta = {
                        "id": lid,
                        "zone": light.get("zone"),
                        "supports": {
                            "state": True,
                            "mode": light.get("mode") is not None,
                            "color": light.get("color") is not None,
                            "brightness": light.get("brightness") is not None,
                            "cycle_speed": light.get("cycle_speed") is not None,
                        },
                        # T052: publish the recommended command topics for this light
                        "state_writetopic": f"{base_topic}/lights/{lid}/state_writetopic",
                        "mode_writetopic": f"{base_topic}/lights/{lid}/mode_writetopic"
                        if light.get("mode") is not None
                        else None,
                        "color_writetopic": f"{base_topic}/lights/{lid}/color_writetopic"
                        if light.get("color") is not None
                        else None,
                        "brightness_writetopic": f"{base_topic}/lights/{lid}/brightness_writetopic"
                        if light.get("brightness") is not None
                        else None,
                        "detected_modes": detected_modes,  # Add detected modes from YAML
                        "last_updated": timestamp,
                    }
                    topic_meta = f"{base_topic}/lights/{lid}/meta"
                    messages.append(
                        MQTTMessage(
                            topic=topic_meta,
                            payload=json.dumps(meta),
                            qos=1,
                            retain=True,
                        )
                    )
                    logger.info(
                        "created-light-meta",
                        extra={"topic": topic_meta, "spa_id": spa_id, "light_id": lid},
                    )
                except Exception as e:  # noqa: BLE001
                    # don't let a meta serialization error break snapshot publish
                    logger.warning(f"Error creating light meta for {lid}: {e}")

            messages.append(
                MQTTMessage(
                    topic=f"{base_topic}/lights/last_updated",
                    payload=str(timestamp),
                    qos=1,
                    retain=True,
                )
            )

            # No legacy (non-spa) per-light topics are published anymore; prefer
            # spa-scoped topics under <base_topic>/<spa_id>/lights/...
        return messages


class MQTTTopicMapper(StateTopicEncoder):
    """Backward-compatible facade composing encoders and MQTT publication."""

    def __init__(
        self,
        config: AppConfig,
        mqtt_client: Any,
        discovery_repository: DiscoveryRepository | None = None,
    ) -> None:
        self.mqtt_client = mqtt_client
        self.discovery_repository = discovery_repository or DiscoveryRepository()
        super().__init__(config, self._load_detected_modes_for_light)
        self._publisher = MqttPublisher(mqtt_client)
        self._metadata_encoder = MetadataTopicEncoder(config.mqtt.base_topic)
        self._discovery_encoder = DiscoveryTopicEncoder(config.mqtt.base_topic)

    def publish_messages(self, messages: list[MQTTMessage]) -> None:
        """Publish encoded messages through the transport boundary."""
        self._publisher.publish(messages)

    def publish_capability_meta(
        self, spa_id: str, capability_profile: dict[str, Any]
    ) -> MQTTMessage:
        """Backward-compatible single-message publisher for capability meta.

        This method keeps the old behaviour for callers/tests that expect one
        aggregated message. New code should prefer
        `publish_capability_meta_entries` which returns separate messages per
        capability entry.
        """
        return self._metadata_encoder.capability(spa_id, capability_profile)

    def publish_capability_meta_entries(
        self, spa_id: str, capability_profile: dict[str, Any]
    ) -> list[MQTTMessage]:
        """Publish capability meta as separate MQTT messages per entry.

        Args:
            spa_id: ID of the spa
            capability_profile: Capability profile dict

        Returns:
            List of MQTTMessage, one per top-level capability_profile entry
        """
        return self._metadata_encoder.capability_entries(spa_id, capability_profile)

    def publish_version_meta(self) -> list[MQTTMessage]:
        """Publish global version metadata.

        Publishes version information to global meta topics:
        - {base_topic}/meta/smarttub-mqtt: smarttub-mqtt version only
        - {base_topic}/meta/python-smarttub: python-smarttub version only

        Returns:
            List of MQTT messages with version information
        """
        return self._metadata_encoder.versions()

    def _load_detected_modes_for_light(self, spa_id: str, light_id: str) -> list[str]:
        """Normalize modes from the repository's in-memory snapshot."""
        try:
            discovered_items = self.discovery_repository.cached_discovered_items()
            return detected_light_modes(discovered_items, spa_id, light_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Error loading detected modes for %s/%s: %s",
                spa_id,
                light_id,
                exc,
            )
            return []

    def publish_discovery_status(self, state: Any) -> list[MQTTMessage]:
        """Encode current discovery status and optional final results."""
        messages = self._discovery_encoder.status(state)
        logger.debug(f"Publishing discovery status: {state.status.value}")
        return messages

    def get_discovery_control_topic(self) -> str:
        """Return the discovery command subscription topic."""
        return self._discovery_encoder.control_topic()


# Convenience function for backward compatibility with tests
def publish_state_snapshot(
    config: AppConfig, snapshot: Mapping[str, Any]
) -> list[MQTTMessage]:
    """Convert a state snapshot into MQTT messages for publishing.

    This is a convenience function that creates a temporary mapper instance.
    In production code, use MQTTTopicMapper class directly.

    Args:
        config: Application configuration
        snapshot: State snapshot with timestamp and components

    Returns:
        List of MQTT messages to publish
    """

    # Create a dummy client for this function (not used in message creation)
    class DummyClient:
        pass

    mapper = MQTTTopicMapper(config, DummyClient())
    return mapper.publish_state_snapshot(snapshot)
