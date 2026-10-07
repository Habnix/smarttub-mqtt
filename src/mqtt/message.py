"""Transport-neutral MQTT message value object."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MQTTMessage:
    """One MQTT publication produced by an encoder."""

    topic: str
    payload: str
    qos: int = 1
    retain: bool = True
