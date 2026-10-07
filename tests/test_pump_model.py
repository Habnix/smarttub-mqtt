"""Contract tests for model-neutral pump state and capabilities."""

from types import SimpleNamespace

import pytest

from src.core.capability_detector import CapabilityDetector, SpaCapabilities
from src.core.pump_model import (
    normalize_pump_role,
    normalize_pump_state,
    normalize_speed_capability,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("OFF", ("off", "off")),
        ("LOW", ("on", "low")),
        ("HIGH", ("on", "high")),
        ("ON", ("on", "unknown")),
        ("vendor_new_state", ("unknown", "unknown")),
    ],
)
def test_pump_state_does_not_turn_low_or_unknown_into_off(raw, expected):
    assert normalize_pump_state(raw) == expected


def test_pump_role_and_speed_capability_are_independent():
    assert normalize_pump_role("JET") == "jet"
    assert normalize_speed_capability(2) == "two_speed"
    assert normalize_pump_role("future_vendor_role") == "unknown"
    assert normalize_speed_capability("future_vendor_speed") == "unknown"


@pytest.mark.asyncio
async def test_capability_detector_uses_observed_per_pump_speed_counts():
    pumps = [
        SimpleNamespace(id="P1", type="JET", speed=2),
        SimpleNamespace(id="P2", type="JET", speed=1),
        SimpleNamespace(id="CP", type="CIRCULATION", speed=None),
    ]

    class Spa:
        @staticmethod
        async def get_pumps():
            return pumps

    detector = object.__new__(CapabilityDetector)
    capabilities = SpaCapabilities("spa-test")

    await detector._detect_pump_capabilities(capabilities, Spa())

    assert capabilities.pump_speeds == ["high", "low"]
    assert capabilities.pumps == [
        {
            "id": "P1",
            "type": "jet",
            "speed_capability": "two_speed",
            "supported_speeds": ["low", "high"],
        },
        {
            "id": "P2",
            "type": "jet",
            "speed_capability": "one_speed",
            "supported_speeds": ["high"],
        },
        {
            "id": "CP",
            "type": "circulation",
            "speed_capability": "unknown",
            "supported_speeds": [],
        },
    ]


def test_failed_capability_detection_does_not_assume_hardware_support():
    detector = object.__new__(CapabilityDetector)

    capabilities = detector._get_minimal_capabilities("spa-test")

    assert capabilities.detection_status == "unknown"
    assert capabilities.heater_supported is False
    assert capabilities.pump_supported is False
    assert capabilities.light_supported is False
