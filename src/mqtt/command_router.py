"""Pure MQTT command-topic routing helpers."""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CommandRoute:
    """Resolved command information passed from MQTT to a command handler."""

    spa_id: str | None
    command_path: str
    handler_key: str
    data: Any


class CommandRouter:
    """Resolve MQTT topics without knowing anything about SmartTub actions."""

    def __init__(self, base_topic: str):
        self.base_topic = base_topic

    def resolve(
        self, topic: str, payload: Any, handler_keys: Collection[str]
    ) -> CommandRoute:
        """Resolve a topic into a handler key and normalized payload."""
        remainder = self._strip_base_topic(topic)
        parts = remainder.split("/", 1)
        if len(parts) == 2:
            spa_id, command_path = parts
        else:
            spa_id, command_path = None, remainder

        handler_key = command_path
        data = self.parse_payload(payload)

        if handler_key == command_path:
            pump_route = self._resolve_pump_route(command_path, handler_keys, data)
            if pump_route is not None:
                handler_key, data = pump_route

            light_route = self._resolve_light_route(command_path, handler_keys, data)
            if light_route is not None:
                handler_key, data = light_route

        return CommandRoute(
            spa_id=spa_id,
            command_path=command_path,
            handler_key=handler_key,
            data=data,
        )

    def _strip_base_topic(self, topic: str) -> str:
        prefix = f"{self.base_topic}/"
        return topic.removeprefix(prefix)

    @classmethod
    def _resolve_pump_route(
        cls, command_path: str, handler_keys: Collection[str], data: Any
    ) -> tuple[str, dict[str, Any]] | None:
        parts = command_path.split("/", 2)
        if (
            not command_path.startswith("pumps/")
            or len(parts) != 3
            or parts[2] != "state_writetopic"
        ):
            return None

        handler_key = "pumps/state_writetopic"
        if handler_key not in handler_keys:
            return None
        return handler_key, cls.normalize_data(data, pump_id=parts[1])

    @classmethod
    def _resolve_light_route(
        cls, command_path: str, handler_keys: Collection[str], data: Any
    ) -> tuple[str, dict[str, Any]] | None:
        parts = command_path.split("/", 2)
        if (
            not command_path.startswith("lights/")
            or len(parts) != 3
            or not parts[2].endswith("_writetopic")
        ):
            return None

        handler_key = f"lights/{parts[2]}"
        if handler_key not in handler_keys:
            return None
        return handler_key, cls.normalize_data(data, light_id=parts[1])

    @staticmethod
    def parse_payload(payload: Any) -> Any:
        """Decode MQTT bytes and parse JSON payloads when possible."""
        if isinstance(payload, (bytes, bytearray, memoryview)):
            payload = bytes(payload).decode("utf-8")
        elif not isinstance(payload, str):
            payload = str(payload)

        try:
            return json.loads(payload)
        except (json.JSONDecodeError, TypeError, ValueError):
            return payload

    @staticmethod
    def normalize_data(
        raw_data: Any, pump_id: str | None = None, light_id: str | None = None
    ) -> dict[str, Any]:
        """Normalize scalar payloads and inject per-component identifiers."""
        if isinstance(raw_data, dict):
            data = raw_data.copy()
        else:
            value_str = str(raw_data).strip()
            if value_str.lower() in ("on", "off"):
                data = {"state": value_str.lower()}
            elif value_str.isdigit():
                data = {"value": int(value_str)}
            else:
                data = {"value": value_str}

        if pump_id:
            data["pump_id"] = pump_id
        if light_id:
            data["light_id"] = light_id
        return data
