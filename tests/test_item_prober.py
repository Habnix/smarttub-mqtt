from types import SimpleNamespace

import pytest

from src.core.item_prober import ItemProber


class _InventorySpa:
    id = "spa-1"
    brand = "Test"

    async def get_status(self):
        return SimpleNamespace(
            heater1Present=True,
            water=SimpleNamespace(temperature=37.5),
            online=True,
        )

    async def get_status_full(self):
        return {"online": True}

    async def get_debug_status(self):
        return {"debug": "ok"}

    async def get_energy_usage(self):
        raise RuntimeError("not supported")

    async def get_errors(self):
        return []

    async def get_reminders(self):
        return []

    async def get_pumps(self):
        return {
            "pumps": [
                {
                    "id": "P1",
                    "type": "JET",
                    "state": "OFF",
                    "speed": "ONE_SPEED",
                    "spa": {"duplicate": True},
                }
            ]
        }

    async def get_lights(self):
        return [
            {
                "zone": 1,
                "intensity": 50,
                "color": {"red": 1, "green": 2, "blue": 3},
                "cycleSpeed": 2,
                "spa": {"duplicate": True},
            }
        ]


def _prober():
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub"),
        safety=SimpleNamespace(command_timeout_seconds=1),
        discovery_test_all_light_modes=False,
    )
    return ItemProber(config, SimpleNamespace(spas=[]), SimpleNamespace())


@pytest.mark.asyncio
async def test_spa_inventory_normalizes_dict_collections_and_isolates_errors():
    result = await _prober()._probe_spa(_InventorySpa())

    assert result["heater"] == {"present": True, "water_temperature": 37.5}
    assert result["pumps"][0]["supports"] == {"state": True, "speed": True}
    assert result["pumps"][0]["raw"].get("spa") is None
    assert result["pumps"][0]["state_writetopic"] == (
        "smarttub/spa-1/pumps/P1/state_writetopic"
    )
    assert result["lights"][0]["id"] == "zone_1"
    assert result["lights"][0]["supports"] == {
        "color": True,
        "brightness": True,
        "cycle_speed": True,
    }
    assert result["lights"][0]["raw"].get("spa") is None
    assert result["errors"] == ["energy_usage_error: not supported"]


def test_light_inventory_preserves_zone_zero():
    item = _prober()._light_inventory_item({"zone": 0, "intensity": 0})

    assert item["id"] == "zone_0"
