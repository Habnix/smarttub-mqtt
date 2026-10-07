"""Contract tests for the centralized python-smarttub compatibility boundary."""

import asyncio

import pytest

from src.core.smarttub_gateway import SmartTubGateway


class Spa:
    def __init__(self):
        self.calls = []

    async def request(self, method, endpoint, *body):
        self.calls.append((method, endpoint, body))
        if endpoint == "lights":
            return {"lights": [{"zone": 1, "color": {"red": 0}}]}
        return {"ok": True}


@pytest.mark.asyncio
async def test_gateway_preserves_two_argument_get_compatibility():
    spa = Spa()
    gateway = SmartTubGateway()

    lights = await gateway.get_raw_lights(spa)

    assert lights == [{"zone": 1, "color": {"red": 0}}]
    assert spa.calls == [("GET", "lights", ())]


@pytest.mark.asyncio
async def test_gateway_centralizes_light_patch_shape():
    spa = Spa()
    gateway = SmartTubGateway()

    await gateway.patch_light(spa, 2, {"mode": "OFF", "intensity": 0})

    assert spa.calls == [("PATCH", "lights/2", ({"mode": "OFF", "intensity": 0},))]


@pytest.mark.asyncio
async def test_gateway_enforces_optional_timeout():
    class SlowSpa:
        @staticmethod
        async def request(_method, _endpoint):
            await asyncio.Event().wait()

    with pytest.raises(TimeoutError):
        await SmartTubGateway().request(SlowSpa(), "GET", "lights", timeout=0.01)
