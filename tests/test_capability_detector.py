"""Behaviour and contract tests for model-neutral capability detection."""

from datetime import UTC, datetime, timedelta
from enum import Enum
from types import SimpleNamespace

import pytest

from src.core.capability_detector import CapabilityDetector, SpaCapabilities
from src.core.discovery_repository import DiscoveryRepository


class _Filtration:
    class PrimaryFiltrationMode(Enum):
        NORMAL = "NORMAL"
        ECO_MODE = "ECO_MODE"


class _Spa:
    id = "spa-test"
    model = "Community Model"
    brand = "Generic"

    def __init__(self):
        self.status_calls = 0

    async def get_status(self):
        self.status_calls += 1
        return SimpleNamespace(
            heater1Present="PRESENT",
            temperature_range={"min": 18, "max": 40},
            primary_filtration=_Filtration(),
            uv="ON",
            ozone="NOT_SUPPORTED",
            nanoStatus="ON",
            water=SimpleNamespace(
                ph=7.2,
                oxidationReductionPotential=650,
                turbidity=None,
            ),
        )

    async def get_pumps(self):
        return [
            SimpleNamespace(id="P1", type="JET", speed=2),
            SimpleNamespace(id="CP", type="CIRCULATION", speed=None),
        ]

    async def get_lights(self):
        return [SimpleNamespace(zone=1)]


class _TopicMapper:
    def __init__(self):
        self.published = []

    @staticmethod
    def publish_capability_meta_entries(spa_id, profile):
        return [("entries", spa_id, profile)]

    @staticmethod
    def publish_capability_meta(spa_id, profile):
        return ("legacy", spa_id, profile)

    def publish_messages(self, messages):
        self.published.append(messages)


def _detector(spa, topic_mapper=None):
    config = SimpleNamespace(
        capability=SimpleNamespace(
            cache_expiry_seconds=60,
            refresh_interval_seconds=300,
        )
    )
    return CapabilityDetector(
        config,
        SimpleNamespace(spas=[] if spa is None else [spa]),
        topic_mapper,
    )


def test_capability_serialization_round_trip_preserves_the_public_contract():
    capabilities = SpaCapabilities("spa-test")
    capabilities.firmware_version = "1.2.3"
    capabilities.model = "Model X"
    capabilities.brand = "Generic"
    capabilities.detection_status = "detected"
    capabilities.heater_supported = True
    capabilities.heater_temperature_range = {"min": 18.0, "max": 40.0}
    capabilities.heater_modes = ["AUTO"]
    capabilities.pump_supported = True
    capabilities.pump_count = 1
    capabilities.pump_speeds = ["high"]
    capabilities.pumps = [{"id": "P1"}]
    capabilities.light_supported = True
    capabilities.light_colors = ["white"]
    capabilities.light_modes = ["OFF", "WHITE"]
    capabilities.light_brightness_supported = True
    capabilities.primary_filtration_supported = True
    capabilities.primary_filtration_modes = ["NORMAL", "ECO_MODE"]
    capabilities.uv_supported = True
    capabilities.water_care_supported = True
    capabilities.ph_monitoring = True

    restored = SpaCapabilities.from_dict(capabilities.to_dict())

    assert restored.to_dict() == capabilities.to_dict()


@pytest.mark.asyncio
async def test_full_detection_uses_observed_data_and_publishes_one_profile():
    spa = _Spa()
    topics = _TopicMapper()
    detector = _detector(spa, topics)

    capabilities = await detector.detect_capabilities("spa-test")

    assert capabilities.detection_status == "detected"
    assert capabilities.heater_temperature_range == {"min": 18.0, "max": 40.0}
    assert capabilities.primary_filtration_modes == ["NORMAL", "ECO_MODE"]
    assert capabilities.pump_count == 2
    assert capabilities.pumps[0]["speed_capability"] == "two_speed"
    assert capabilities.light_supported is True
    assert capabilities.uv_supported is True
    assert capabilities.ozone_supported is False
    assert capabilities.nano_supported is True
    assert capabilities.water_care_supported is True
    assert capabilities.ph_monitoring is True
    assert capabilities.orp_monitoring is True
    assert len(topics.published) == 1
    assert len(topics.published[0]) == 2
    assert detector.get_capability_profile("spa-test")["heater"] == {
        "temperature_range": {"min": 18.0, "max": 40.0},
        "modes": ["AUTO", "ECONOMY", "DAY", "READY", "REST"],
    }

    cached = await detector.detect_capabilities("spa-test")
    assert cached is capabilities
    assert spa.status_calls == 1


@pytest.mark.asyncio
async def test_model_name_alone_never_invents_temperature_limits():
    spa = _Spa()

    async def status_without_limits():
        return SimpleNamespace(heater1Present="PRESENT")

    spa.get_status = status_without_limits
    capabilities = await _detector(spa).detect_capabilities("spa-test")

    assert capabilities.heater_supported is True
    assert capabilities.heater_temperature_range is None


@pytest.mark.asyncio
async def test_detection_failure_is_cached_as_unknown_and_cache_can_be_cleared():
    detector = _detector(None)

    capabilities = await detector.detect_capabilities("missing")

    assert capabilities.detection_status == "unknown"
    assert detector.get_capability_profile("missing")["supported_features"] == {
        "heater": False,
        "pump": False,
        "light": False,
        "filtration": False,
        "water_care": False,
        "advanced": False,
    }
    detector.clear_cache("missing")
    assert detector.get_capability_profile("missing") == {
        "spa_id": "missing",
        "status": "unknown",
    }


def test_cache_expiry_profiles_and_clear_all_are_isolated():
    detector = _detector(None)
    fresh = SpaCapabilities("fresh")
    old = SpaCapabilities("old")
    old.last_updated = datetime.now(UTC) - timedelta(seconds=61)
    detector._capabilities_cache = {"fresh": fresh, "old": old}

    profiles = detector.get_cached_profiles()
    profiles["fresh"]["status"] = "mutated"

    assert detector._is_cache_expired(fresh) is False
    assert detector._is_cache_expired(old) is True
    assert detector.get_capability_profile("fresh")["status"] == "unknown"
    detector.clear_cache()
    assert detector.get_cached_profiles() == {}


@pytest.mark.asyncio
async def test_discovered_yaml_modes_replace_the_unverified_catalog(tmp_path):
    yaml_path = tmp_path / "discovered_items.yaml"
    yaml_path.write_text(
        """
discovered_items:
  spa-test:
    lights:
      - detected_modes: [WHITE, OFF]
      - detected_modes: [PURPLE, WHITE]
""",
        encoding="utf-8",
    )
    capabilities = SpaCapabilities("spa-test")
    detector = _detector(None)
    detector.discovery_repository = DiscoveryRepository(yaml_path)

    await detector._load_detected_modes_from_yaml(capabilities, "spa-test")

    assert capabilities.light_modes == ["OFF", "PURPLE", "WHITE"]


@pytest.mark.asyncio
async def test_refresh_forces_detection_without_duplicate_mqtt_publish():
    spa = _Spa()
    topics = _TopicMapper()
    detector = _detector(spa, topics)
    detector._capabilities_cache["spa-test"] = SpaCapabilities("spa-test")

    await detector.refresh_all_capabilities()

    assert spa.status_calls == 1
    assert len(topics.published) == 1
