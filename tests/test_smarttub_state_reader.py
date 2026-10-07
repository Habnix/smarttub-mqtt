"""Regression tests for the extracted SmartTub state reader."""

from types import SimpleNamespace
from typing import ClassVar

import pytest

from src.core.smarttub_client import SmartTubClient


class _Filtration:
    PrimaryFiltrationMode: ClassVar[list[SimpleNamespace]] = [
        SimpleNamespace(name="NORMAL"),
        SimpleNamespace(name="NANO_MODE"),
        SimpleNamespace(name="ECO_MODE"),
    ]


class _Spa:
    id = "spa-test"

    async def get_status(self):
        return SimpleNamespace(
            water=SimpleNamespace(temperature=38.5),
            heater="ON",
            set_temperature=39.0,
            primary_filtration=SimpleNamespace(
                mode=SimpleNamespace(name="ECO_MODE"),
                cycle=2,
                duration=30,
                start_hour=4,
                status=SimpleNamespace(name="RUNNING"),
            ),
            ambient_temperature=21.0,
            state="READY",
        )

    async def get_pumps(self):
        return []

    async def request(self, method, path):
        return {"lights": []}


@pytest.mark.asyncio
async def test_client_facade_uses_extracted_state_reader():
    config = SimpleNamespace(smarttub=SimpleNamespace(device_id="spa-test"))
    client = SmartTubClient(config)
    client._smarttub_api = object()
    client._spas = [_Spa()]

    snapshot = await client.get_state_snapshot()

    assert snapshot["components"]["filtration"]["mode"] == "ECO_MODE"
    assert snapshot["components"]["filtration"]["supported_modes"] == [
        "NORMAL",
        "NANO_MODE",
        "ECO_MODE",
    ]
    assert snapshot["components"]["spa"]["water_temperature"] == 38.5


@pytest.mark.asyncio
async def test_reader_propagates_component_failures_instead_of_returning_fake_state():
    class BrokenSpa(_Spa):
        async def get_pumps(self):
            raise TimeoutError("pump endpoint unavailable")

    config = SimpleNamespace(smarttub=SimpleNamespace(device_id="spa-test"))
    client = SmartTubClient(config)
    client._smarttub_api = object()
    client._spas = [BrokenSpa()]

    with pytest.raises(RuntimeError, match="pump state"):
        await client.get_state_snapshot()

    assert isinstance(client._last_error, RuntimeError)


@pytest.mark.asyncio
async def test_reader_rejects_missing_spa_instead_of_returning_fake_state():
    config = SimpleNamespace(smarttub=SimpleNamespace(device_id="spa-test"))
    client = SmartTubClient(config)
    client._smarttub_api = object()

    with pytest.raises(RuntimeError, match="No configured SmartTub spa"):
        await client.get_state_snapshot()


@pytest.mark.asyncio
async def test_reader_publishes_low_as_on_without_inventing_one_speed():
    class PumpSpa(_Spa):
        async def get_pumps(self):
            return [
                SimpleNamespace(
                    id="P1",
                    state=SimpleNamespace(name="LOW"),
                    type=SimpleNamespace(name="JET"),
                    speed=2,
                ),
                SimpleNamespace(
                    id="PX",
                    state=SimpleNamespace(name="VENDOR_STATE"),
                    type=SimpleNamespace(name="VENDOR_TYPE"),
                    speed="VENDOR_SPEED",
                ),
            ]

    config = SimpleNamespace(smarttub=SimpleNamespace(device_id="spa-test"))
    client = SmartTubClient(config)
    client._smarttub_api = object()
    client._spas = [PumpSpa()]

    pumps = (await client.get_state_snapshot())["components"]["pumps"]

    assert pumps[0] == {
        "id": "P1",
        "type": "jet",
        "state": "on",
        "speed": "low",
        "speed_capability": "two_speed",
        "supported_speeds": ["low", "high"],
        "raw_state": "LOW",
        "raw_type": "JET",
        "raw_speed_capability": "2",
    }
    assert pumps[1]["state"] == "unknown"
    assert pumps[1]["speed"] == "unknown"
    assert pumps[1]["type"] == "unknown"
    assert pumps[1]["speed_capability"] == "unknown"


@pytest.mark.asyncio
async def test_reader_publishes_off_as_a_known_current_speed():
    class PumpSpa(_Spa):
        async def get_pumps(self):
            return [
                SimpleNamespace(
                    id="P1",
                    state=SimpleNamespace(name="OFF"),
                    type=SimpleNamespace(name="JET"),
                    speed=1,
                )
            ]

    config = SimpleNamespace(smarttub=SimpleNamespace(device_id="spa-test"))
    client = SmartTubClient(config)
    client._smarttub_api = object()
    client._spas = [PumpSpa()]

    pump = (await client.get_state_snapshot())["components"]["pumps"][0]

    assert pump["state"] == "off"
    assert pump["speed"] == "off"
    assert pump["speed_capability"] == "one_speed"


def test_client_selects_only_the_configured_spa():
    config = SimpleNamespace(smarttub=SimpleNamespace(device_id="spa-two"))
    client = SmartTubClient(config)
    first_spa = SimpleNamespace(id="spa-one")
    selected_spa = SimpleNamespace(id="spa-two")

    client._select_configured_spa([first_spa, selected_spa])

    assert client.spas == [selected_spa]


def test_client_rejects_an_unknown_configured_spa():
    config = SimpleNamespace(smarttub=SimpleNamespace(device_id="spa-missing"))
    client = SmartTubClient(config)

    with pytest.raises(
        ValueError, match="SMARTTUB_DEVICE_ID 'spa-missing' was not found"
    ):
        client._select_configured_spa([SimpleNamespace(id="spa-one")])
