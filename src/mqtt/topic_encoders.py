"""Pure encoders for non-telemetry MQTT topics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from src.core.version import get_version_info
from src.mqtt.message import MQTTMessage


class MetadataTopicEncoder:
    """Encode capability and version metadata without transport I/O."""

    def __init__(self, base_topic: str) -> None:
        self.base_topic = base_topic

    def capability(self, spa_id: str, profile: Mapping[str, Any]) -> MQTTMessage:
        topic = (
            f"{self.base_topic}/{spa_id}/spa/capability/meta"
            if spa_id
            else f"{self.base_topic}/spa/{spa_id}/capability/meta"
        )
        return MQTTMessage(topic=topic, payload=json.dumps(profile))

    def capability_entries(
        self, spa_id: str, profile: Mapping[str, Any]
    ) -> list[MQTTMessage]:
        base = (
            f"{self.base_topic}/{spa_id}/spa/capability"
            if spa_id
            else f"{self.base_topic}/spa/capability"
        )
        messages: list[MQTTMessage] = []
        for key, value in profile.items():
            payload = (
                ""
                if value is None
                else str(value)
                if isinstance(value, (str, int, float, bool))
                else json.dumps(value)
            )
            messages.append(MQTTMessage(topic=f"{base}/{key}", payload=payload))
        return messages

    def versions(self) -> list[MQTTMessage]:
        versions = get_version_info()
        return [
            MQTTMessage(
                topic=f"{self.base_topic}/meta/smarttub-mqtt",
                payload=versions["smarttub_mqtt"],
            ),
            MQTTMessage(
                topic=f"{self.base_topic}/meta/python-smarttub",
                payload=versions["python_smarttub"],
            ),
        ]


class DiscoveryTopicEncoder:
    """Encode discovery state without accessing MQTT or persistence."""

    def __init__(self, base_topic: str) -> None:
        self.base_topic = base_topic

    def status(self, state: Any) -> list[MQTTMessage]:
        status_data = {
            "status": state.status.value,
            "mode": state.mode.value if state.mode else None,
            "started_at": state.started_at.isoformat() if state.started_at else None,
            "completed_at": (
                state.completed_at.isoformat() if state.completed_at else None
            ),
            "progress": {
                "percentage": state.progress.percentage,
                "current_spa": state.progress.current_spa,
                "current_light": state.progress.current_light,
                "lights_total": state.progress.lights_total,
                "lights_tested": state.progress.lights_tested,
                "modes_total": state.progress.modes_total,
                "modes_tested": state.progress.modes_tested,
            },
            "error": state.error,
        }
        messages = [
            MQTTMessage(
                topic=f"{self.base_topic}/discovery/status",
                payload=json.dumps(status_data, indent=2),
                retain=False,
            )
        ]
        if state.status.value == "completed" and state.results:
            result_data = {
                "completed_at": (
                    state.completed_at.isoformat() if state.completed_at else None
                ),
                "yaml_path": state.results.yaml_path,
                "total_lights": state.results.total_lights,
                "total_modes_detected": state.results.total_modes_detected,
                "spas": state.results.spas,
            }
            messages.append(
                MQTTMessage(
                    topic=f"{self.base_topic}/discovery/result",
                    payload=json.dumps(result_data, indent=2),
                )
            )
        return messages

    def control_topic(self) -> str:
        return f"{self.base_topic}/discovery/control"


def detected_light_modes(
    discovered_items: Mapping[str, Any], spa_id: str, light_id: str
) -> list[str]:
    """Normalize modes for one light from an already loaded document."""
    spa_data = discovered_items.get(spa_id)
    if not isinstance(spa_data, Mapping):
        return []
    lights = spa_data.get("lights", [])
    if not isinstance(lights, list):
        return []
    light = next(
        (
            candidate
            for candidate in lights
            if isinstance(candidate, Mapping) and candidate.get("id") == light_id
        ),
        None,
    )
    if light is None:
        return []
    modes = light.get("detected_modes", [])
    if not isinstance(modes, list):
        return []
    return [
        "OFF" if mode is False else "ON" if mode is True else mode.strip().upper()
        for mode in modes
        if isinstance(mode, (str, bool)) and (not isinstance(mode, str) or mode.strip())
    ]
