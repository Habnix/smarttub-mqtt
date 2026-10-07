"""I/O-free contracts for MQTT metadata and discovery encoders."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from src.mqtt.message import MQTTMessage
from src.mqtt.publisher import MqttPublisher
from src.mqtt.topic_encoders import (
    DiscoveryTopicEncoder,
    MetadataTopicEncoder,
    detected_light_modes,
)
from src.mqtt.topic_mapper import StateTopicEncoder


def test_state_encoder_needs_neither_broker_nor_repository() -> None:
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub"),
        smarttub=SimpleNamespace(device_id=None),
    )
    encoder = StateTopicEncoder(
        config,
        detected_modes_lookup=lambda spa_id, light_id: [f"{spa_id}:{light_id}:WHEEL"],
    )

    messages = encoder.publish_state_snapshot(
        {
            "spa_id": "spa-1",
            "timestamp": "2026-08-22T00:00:00+00:00",
            "components": {"lights": [{"id": "zone-1", "state": "on"}]},
        }
    )

    light_meta = next(
        message for message in messages if message.topic.endswith("/lights/zone-1/meta")
    )
    assert json.loads(light_meta.payload)["detected_modes"] == ["spa-1:zone-1:WHEEL"]


def test_metadata_encoder_needs_no_mqtt_client() -> None:
    encoder = MetadataTopicEncoder("smarttub")

    aggregate = encoder.capability("spa-1", {"pump_count": 2})
    entries = encoder.capability_entries(
        "spa-1", {"pump_count": 2, "pumps": [{"id": "P1"}], "model": None}
    )

    assert aggregate.topic == "smarttub/spa-1/spa/capability/meta"
    assert json.loads(aggregate.payload) == {"pump_count": 2}
    assert {message.topic: message.payload for message in entries} == {
        "smarttub/spa-1/spa/capability/pump_count": "2",
        "smarttub/spa-1/spa/capability/pumps": '[{"id": "P1"}]',
        "smarttub/spa-1/spa/capability/model": "",
    }


def test_discovery_encoder_is_pure_and_preserves_retain_contract() -> None:
    now = datetime(2026, 8, 22, tzinfo=UTC)
    state = SimpleNamespace(
        status=SimpleNamespace(value="completed"),
        mode=SimpleNamespace(value="quick"),
        started_at=now,
        completed_at=now,
        progress=SimpleNamespace(
            percentage=100.0,
            current_spa="spa-1",
            current_light="zone-1",
            lights_total=1,
            lights_tested=1,
            modes_total=2,
            modes_tested=2,
        ),
        error=None,
        results=SimpleNamespace(
            yaml_path="/config/discovered_items.yaml",
            total_lights=1,
            total_modes_detected=2,
            spas={"spa-1": {}},
        ),
    )

    messages = DiscoveryTopicEncoder("smarttub").status(state)

    assert [message.topic for message in messages] == [
        "smarttub/discovery/status",
        "smarttub/discovery/result",
    ]
    assert messages[0].retain is False
    assert messages[1].retain is True


def test_detected_light_mode_encoder_handles_yaml_booleans_without_io() -> None:
    items = {
        "spa-1": {
            "lights": [{"id": "zone-1", "detected_modes": [False, True, " purple ", 7]}]
        }
    }

    assert detected_light_modes(items, "spa-1", "zone-1") == [
        "OFF",
        "ON",
        "PURPLE",
    ]


def test_publisher_is_the_only_component_that_calls_the_broker() -> None:
    calls = []
    broker = SimpleNamespace(
        publish_sync=lambda **kwargs: calls.append(kwargs),
    )

    MqttPublisher(broker).publish(
        [MQTTMessage("smarttub/spa-1/state", "on", qos=1, retain=True)]
    )

    assert calls == [
        {
            "topic": "smarttub/spa-1/state",
            "payload": "on",
            "qos": 1,
            "retain": True,
        }
    ]
