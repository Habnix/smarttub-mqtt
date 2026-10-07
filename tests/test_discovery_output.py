import json
from copy import deepcopy
from types import SimpleNamespace

import yaml

from src.core.discovery_output import DiscoveryFileRepository, DiscoveryMqttPublisher
from src.mqtt.topic_mapper import MQTTMessage


class _Mapper:
    def __init__(self):
        self.snapshots = []
        self.messages = []

    def publish_state_snapshot(self, snapshot):
        self.snapshots.append(snapshot)
        return [MQTTMessage("snapshot/topic", "mapped")]

    def publish_messages(self, messages):
        self.messages.extend(messages)


def test_file_repository_splits_documents_without_mutating_input(tmp_path):
    results = {
        "spa-1": {
            "spa_id": "spa-1",
            "spa": {"name": "Garden", "model": "J", "id": "private"},
            "pumps": [
                {
                    "id": "P1",
                    "state_writetopic": "smarttub/spa-1/pumps/P1/state_writetopic",
                }
            ],
            "status_full": {"online": True},
            "custom_diagnostic": 42,
        }
    }
    original = deepcopy(results)
    repository = DiscoveryFileRepository(primary_dir=tmp_path)

    compact_path, raw_path = repository.save(results)

    assert results == original
    compact = yaml.safe_load(compact_path.read_text())
    raw = yaml.safe_load(raw_path.read_text())
    assert compact["discovered_items"]["spa-1"]["spa"] == {
        "name": "Garden",
        "model": "J",
    }
    assert (
        compact["discovered_items"]["spa-1"]["pumps"][0]["state_writetopic"]
        == "pumps/P1/state_writetopic"
    )
    assert raw["discovered_items"]["spa-1"]["status_full"] == {"online": True}
    assert raw["discovered_items"]["spa-1"]["custom_diagnostic"] == 42


def test_file_repository_uses_fallback_when_primary_is_not_a_directory(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("file")
    fallback = tmp_path / "fallback"
    repository = DiscoveryFileRepository(
        primary_dir=blocked,
        fallback_dir=fallback,
    )

    paths = repository.save({"spa-1": {"spa_id": "spa-1"}})

    assert paths == (
        fallback / "discovered_items.yaml",
        fallback / "spa_raw_data.yaml",
    )


def test_mqtt_publisher_maps_pumps_and_scopes_results_to_each_spa():
    mapper = _Mapper()
    config = SimpleNamespace(mqtt=SimpleNamespace(base_topic="smarttub"))
    publisher = DiscoveryMqttPublisher(config, mapper)
    results = {
        "spa-1": {
            "spa_id": "spa-1",
            "discovered_at": "2026-08-22T00:00:00+00:00",
            "pumps": [
                {
                    "id": "P1",
                    "raw": {"properties": {"state": "LOW", "speed": "TWO_SPEED"}},
                    "supports": {"state": True, "speed": True},
                }
            ],
        },
        "spa-2": {"spa_id": "spa-2", "pumps": []},
    }

    publisher.publish_pump_metadata(results)
    publisher.publish_results(results)

    assert mapper.snapshots[0]["components"]["pumps"][0]["state"] == "LOW"
    topics = {message.topic for message in mapper.messages}
    assert "smarttub/spa-1/pumps/P1/meta" in topics
    assert "smarttub/spa-1/discovery/result" in topics
    assert "smarttub/spa-2/discovery/result" in topics
    meta = next(
        message
        for message in mapper.messages
        if message.topic == "smarttub/spa-1/pumps/P1/meta"
    )
    assert json.loads(meta.payload)["state_writetopic"] == (
        "smarttub/spa-1/pumps/P1/state_writetopic"
    )
