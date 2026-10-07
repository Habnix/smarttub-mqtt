"""Smoke tests for the SmartTub 0.0.48 feature mappings."""

import json
from types import SimpleNamespace

from src.core.discovery_repository import DiscoveryRepository
from src.mqtt.topic_mapper import MQTTTopicMapper


def test_maps_primary_filtration_eco_mode_and_light_cycle_speed() -> None:
    """Publish the new filtration and color-light fields as MQTT state."""
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id="spa-test"),
    )
    mapper = MQTTTopicMapper(config, mqtt_client=None)

    messages = mapper.publish_state_snapshot(
        {
            "spa_id": "spa-test",
            "timestamp": "2026-08-16T10:00:00+00:00",
            "components": {
                "filtration": {
                    "mode": "ECO_MODE",
                    "supported_modes": ["NORMAL", "NANO_MODE", "ECO_MODE"],
                },
                "lights": [
                    {
                        "id": "zone_1",
                        "state": "on",
                        "cycle_speed": 7,
                    }
                ],
            },
        }
    )

    payloads = {message.topic: message.payload for message in messages}

    assert payloads["smarttub-mqtt/spa-test/filtration/mode"] == "ECO_MODE"
    assert payloads["smarttub-mqtt/spa-test/lights/zone_1/cycle_speed"] == "7"

    filtration_meta = json.loads(payloads["smarttub-mqtt/spa-test/filtration/meta"])
    assert "ECO_MODE" in filtration_meta["supported_modes"]
    assert (
        filtration_meta["mode_writetopic"]
        == "smarttub-mqtt/spa-test/filtration/mode_writetopic"
    )


def test_detected_light_modes_are_typed_and_yaml_booleans_keep_domain_meaning(
    tmp_path,
) -> None:
    path = tmp_path / "discovered_items.yaml"
    path.write_text(
        """
discovered_items:
  spa-test:
    lights:
      - id: zone_1
        detected_modes: [OFF, ON, " purple ", 3, "", null]
""",
        encoding="utf-8",
    )
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id="spa-test"),
    )

    repository = DiscoveryRepository(path)
    repository.read()
    modes = MQTTTopicMapper(
        config,
        mqtt_client=None,
        discovery_repository=repository,
    )._load_detected_modes_for_light("spa-test", "zone_1")

    assert modes == ["OFF", "ON", "PURPLE"]


def test_maps_retained_availability_and_quality_separately_from_telemetry() -> None:
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id="spa-test"),
    )
    mapper = MQTTTopicMapper(config, mqtt_client=None)

    messages = mapper.publish_state_quality(
        spa_id="spa-test",
        status="stale",
        observed_at="2026-08-16T10:00:00+00:00",
        last_success_at="2026-08-16T10:00:00+00:00",
        checked_at="2026-08-16T10:01:00+00:00",
    )

    by_topic = {message.topic: message for message in messages}
    availability = by_topic["smarttub-mqtt/spa-test/availability"]
    quality = by_topic["smarttub-mqtt/spa-test/state/quality"]
    assert availability.payload == "offline"
    assert availability.retain is True
    assert json.loads(quality.payload) == {
        "status": "stale",
        "observed_at": "2026-08-16T10:00:00+00:00",
        "last_success_at": "2026-08-16T10:00:00+00:00",
        "checked_at": "2026-08-16T10:01:00+00:00",
    }
    assert quality.retain is True


def test_maps_pump_speed_capability_without_assuming_speed_support() -> None:
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id="spa-test"),
    )
    mapper = MQTTTopicMapper(config, mqtt_client=None)

    messages = mapper.publish_state_snapshot(
        {
            "spa_id": "spa-test",
            "timestamp": "2026-08-16T10:00:00+00:00",
            "components": {
                "pumps": [
                    {
                        "id": "P1",
                        "type": "jet",
                        "state": "on",
                        "speed": "low",
                        "speed_capability": "two_speed",
                        "supported_speeds": ["low", "high"],
                    },
                    {
                        "id": "P2",
                        "type": "jet",
                        "state": "off",
                        "speed": "off",
                        "speed_capability": "one_speed",
                        "supported_speeds": ["high"],
                    },
                ]
            },
        }
    )

    payloads = {message.topic: message.payload for message in messages}
    assert payloads["smarttub-mqtt/spa-test/pumps/P1/state"] == "on"
    assert payloads["smarttub-mqtt/spa-test/pumps/P1/speed"] == "low"
    assert payloads["smarttub-mqtt/spa-test/pumps/P1/speed_capability"] == "two_speed"
    assert payloads["smarttub-mqtt/spa-test/pumps/P2/state"] == "off"
    assert payloads["smarttub-mqtt/spa-test/pumps/P2/speed"] == "off"
    meta = json.loads(payloads["smarttub-mqtt/spa-test/pumps/P1/meta"])
    assert meta["supported_speeds"] == ["low", "high"]
