"""MQTT publication boundary, separate from topic encoding."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Protocol

from src.mqtt.message import MQTTMessage

logger = logging.getLogger(__name__)


class SyncMqttClient(Protocol):
    """Minimal broker contract required by the synchronous publication edge."""

    def publish_sync(
        self, *, topic: str, payload: str, qos: int, retain: bool
    ) -> Any: ...


class MqttPublisher:
    """Send already encoded messages through the configured broker adapter."""

    def __init__(self, mqtt_client: SyncMqttClient) -> None:
        self.mqtt_client = mqtt_client

    def publish(self, messages: Iterable[MQTTMessage]) -> None:
        for message in messages:
            try:
                logger.info(
                    "publishing-mqtt-message",
                    extra={
                        "topic": message.topic,
                        "payload_len": len(message.payload),
                        "qos": message.qos,
                        "retain": message.retain,
                    },
                )
                self.mqtt_client.publish_sync(
                    topic=message.topic,
                    payload=message.payload,
                    qos=message.qos,
                    retain=message.retain,
                )
            except Exception as exc:
                logger.warning(
                    "mqtt-publish-error",
                    exc_info=exc,
                    extra={"topic": message.topic},
                )
