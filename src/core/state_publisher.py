"""Publish state snapshots without coupling synchronization to MQTT details."""

from __future__ import annotations

from typing import Any

from src.core.state_models import StateSnapshot
from src.mqtt.topic_mapper import MQTTTopicMapper


class StatePublisher:
    """Translate and publish snapshots through the configured topic mapper."""

    def __init__(self, topic_mapper: MQTTTopicMapper):
        self.topic_mapper = topic_mapper

    def publish(self, snapshot: StateSnapshot | dict[str, Any]) -> int:
        """Publish one complete snapshot and return the message count."""
        messages = self.topic_mapper.publish_state_snapshot(snapshot)
        self.topic_mapper.publish_messages(messages)
        return len(messages)
