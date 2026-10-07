"""Tests for persistence of background discovery results."""

import yaml

from src.core.discovery_result_store import DiscoveryResultStore


def test_result_store_updates_modes_and_preserves_existing_light_data(tmp_path):
    path = tmp_path / "discovered_items.yaml"
    path.write_text(
        yaml.dump(
            {
                "discovered_items": {
                    "spa-one": {
                        "pumps": [{"id": "pump-1"}],
                        "lights": [{"id": "zone_1", "raw": {"keep": True}}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    saved_path = DiscoveryResultStore(path).save_light_modes(
        {
            "spas": {
                "spa-one": {
                    "lights": [
                        {"id": "zone_1", "detected_modes": ["ON", "WHITE"]},
                        {"id": "zone_2", "detected_modes": ["OFF"]},
                    ]
                }
            }
        }
    )

    data = yaml.safe_load(saved_path.read_text(encoding="utf-8"))
    spa = data["discovered_items"]["spa-one"]
    assert spa["pumps"] == [{"id": "pump-1"}]
    assert spa["lights"] == [
        {"id": "zone_1", "raw": {"keep": True}, "detected_modes": ["ON", "WHITE"]},
        {"id": "zone_2", "detected_modes": ["OFF"]},
    ]


def test_result_store_persists_probe_details_and_restore_status(tmp_path):
    path = tmp_path / "discovered_items.yaml"

    saved_path = DiscoveryResultStore(path).save_light_modes(
        {
            "spas": {
                "spa-one": {
                    "lights": [
                        {
                            "id": "zone_1",
                            "detected_modes": ["WHITE"],
                            "mode_results": {
                                "WHITE": {"status": "supported", "elapsed_ms": 120}
                            },
                            "state_restored": True,
                        }
                    ]
                }
            }
        }
    )

    light = yaml.safe_load(saved_path.read_text(encoding="utf-8"))["discovered_items"][
        "spa-one"
    ]["lights"][0]
    assert light["mode_results"]["WHITE"]["status"] == "supported"
    assert light["state_restored"] is True


def test_result_store_returns_normalized_detected_modes(tmp_path):
    store = DiscoveryResultStore(tmp_path / "discovered_items.yaml")
    store.save_light_modes(
        {
            "spas": {
                "spa-one": {"lights": [{"id": "zone_1", "detected_modes": ["white"]}]}
            }
        }
    )

    assert store.get_detected_modes("spa-one", "zone_1") == ["WHITE"]
    assert store.get_detected_modes("spa-one", "zone_9") == []


def test_result_store_persists_and_reloads_last_run_metadata(tmp_path):
    store = DiscoveryResultStore(tmp_path / "discovered_items.yaml")
    store.save_light_modes(
        {
            "spas": {
                "spa-one": {
                    "lights": [
                        {
                            "id": "zone_1",
                            "zone": 1,
                            "detected_modes": ["WHITE"],
                            "mode_results": {"WHITE": {"status": "supported"}},
                            "state_restored": True,
                        }
                    ]
                }
            }
        },
        run_metadata={
            "mode": "full",
            "started_at": "2026-08-22T05:00:00+00:00",
            "completed_at": "2026-08-22T05:01:00+00:00",
            "total_lights": 1,
            "total_modes_detected": 1,
        },
    )

    last_run = store.load_last_run()

    assert last_run is not None
    assert last_run["mode"] == "full"
    assert last_run["completed_at"] == "2026-08-22T05:01:00+00:00"
    assert (
        last_run["results"]["spas"]["spa-one"]["lights"][0]["mode_results"]["WHITE"][
            "status"
        ]
        == "supported"
    )
