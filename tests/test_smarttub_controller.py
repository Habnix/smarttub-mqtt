"""Regression tests for the SmartTub control facade."""

from enum import Enum
from types import SimpleNamespace

import pytest

from src.core.command_models import (
    CloudCommandError,
    CommandStatus,
    CommandVerificationError,
    ComponentNotFoundError,
    UnsupportedCommandError,
)
from src.core.smarttub_client import SmartTubClient


class _Spa:
    def __init__(self):
        self.temperature = None

    async def set_temperature(self, value):
        self.temperature = value


class _FailingTemperatureSpa:
    async def set_temperature(self, _value):
        raise RuntimeError("cloud unavailable")


class _UnverifiedTemperatureSpa:
    async def set_temperature(self, _value):
        raise RuntimeError("State change not reflected within timeout period")


class _HeatSpa:
    class HeatMode(Enum):
        AUTO = "AUTO"

    def __init__(self, *, fail=False):
        self.fail = fail
        self.mode = None

    async def set_heat_mode(self, mode):
        if self.fail:
            raise RuntimeError("cloud unavailable")
        self.mode = mode


class _Filtration:
    class PrimaryFiltrationMode(Enum):
        NORMAL = "NORMAL"
        ECO_MODE = "ECO_MODE"

    def __init__(self, *, fail=False):
        self.fail = fail
        self.mode = None

    async def set(self, *, mode):
        if self.fail:
            raise RuntimeError("cloud unavailable")
        self.mode = mode


class _FiltrationSpa:
    def __init__(self, filtration=None, *, fail_read=False):
        self.filtration = filtration
        self.fail_read = fail_read

    async def get_status(self):
        if self.fail_read:
            raise RuntimeError("cloud unavailable")
        return SimpleNamespace(primary_filtration=self.filtration)


class _LightSpa:
    def __init__(self):
        self.requests = []

    async def get_lights(self):
        return [SimpleNamespace(zone=2)]

    async def request(self, method, path, body=None):
        self.requests.append((method, path, body))


class _FailingLightSpa(_LightSpa):
    async def request(self, method, path, body=None):
        raise RuntimeError("cloud unavailable")


class _RawLightSpa(_LightSpa):
    def __init__(self, raw_light):
        super().__init__()
        self.raw_light = raw_light

    async def request(self, method, path, body=None):
        self.requests.append((method, path, body))
        if method == "GET":
            return {"lights": [self.raw_light]}
        return None


class _Pump:
    def __init__(self, pump_id, states, *, fail_toggle=False, toggle_error=None):
        self.id = pump_id
        self._states = states
        self._index = 0
        self.fail_toggle = fail_toggle
        self.toggle_error = toggle_error
        self.toggle_count = 0

    @property
    def state(self):
        return SimpleNamespace(name=self._states[self._index])

    async def toggle(self):
        if self.toggle_error is not None:
            raise self.toggle_error
        if self.fail_toggle:
            raise RuntimeError("cloud unavailable")
        self.toggle_count += 1
        if self._index + 1 < len(self._states):
            self._index += 1


class _PumpSpa:
    def __init__(self, pumps=None):
        self.pumps = pumps or []

    async def get_pumps(self):
        return self.pumps


@pytest.mark.asyncio
async def test_client_facade_delegates_control_to_controller():
    client = SmartTubClient(SimpleNamespace())
    spa = _Spa()
    client._spas = [spa]

    status = await client.set_temperature(38.5)

    assert spa.temperature == 38.5
    assert status is CommandStatus.CONFIRMED


@pytest.mark.asyncio
async def test_temperature_cloud_failure_is_a_domain_error():
    client = SmartTubClient(SimpleNamespace())
    client._spas = [_FailingTemperatureSpa()]

    with pytest.raises(CloudCommandError, match="target temperature"):
        await client.set_temperature(38.5)


@pytest.mark.asyncio
async def test_temperature_readback_timeout_is_unknown_not_failed():
    client = SmartTubClient(SimpleNamespace())
    client._spas = [_UnverifiedTemperatureSpa()]

    status = await client.set_temperature(26.0)

    assert status is CommandStatus.UNKNOWN


@pytest.mark.asyncio
async def test_heat_mode_success_and_cloud_failure():
    spa = _HeatSpa()
    client = SmartTubClient(SimpleNamespace())
    client._spas = [spa]

    await client.set_heat_mode(" auto ")
    assert spa.mode is _HeatSpa.HeatMode.AUTO

    client._spas = [_HeatSpa(fail=True)]
    with pytest.raises(CloudCommandError, match="heat mode AUTO"):
        await client.set_heat_mode("AUTO")


@pytest.mark.asyncio
async def test_primary_filtration_success_and_failure_paths():
    filtration = _Filtration()
    client = SmartTubClient(SimpleNamespace())
    client._spas = [_FiltrationSpa(filtration)]

    await client.set_primary_filtration_mode("eco_mode")
    assert filtration.mode is _Filtration.PrimaryFiltrationMode.ECO_MODE

    client._spas = [_FiltrationSpa(_Filtration(fail=True))]
    with pytest.raises(CloudCommandError, match="filtration mode NORMAL"):
        await client.set_primary_filtration_mode("NORMAL")

    client._spas = [_FiltrationSpa(fail_read=True)]
    with pytest.raises(CloudCommandError, match="read primary filtration"):
        await client.set_primary_filtration_mode("NORMAL")


@pytest.mark.asyncio
async def test_light_mode_does_not_send_fake_intensity_for_wheel_modes():
    client = SmartTubClient(SimpleNamespace())
    spa = _LightSpa()
    client._spas = [spa]

    await client.set_light_mode("HIGH_SPEED_WHEEL", light_id="zone_2")

    assert spa.requests == [("PATCH", "lights/2", {"mode": "HIGH_SPEED_WHEEL"})]


@pytest.mark.asyncio
async def test_light_mode_propagates_cloud_failures():
    client = SmartTubClient(SimpleNamespace())
    client._spas = [_FailingLightSpa()]

    with pytest.raises(CloudCommandError, match="light mode"):
        await client.set_light_mode("WHITE", light_id="zone_2")


@pytest.mark.asyncio
async def test_light_state_uses_observed_rgb_and_reports_cloud_failure():
    spa = _RawLightSpa(
        {
            "zone": 2,
            "mode": "FULL_DYNAMIC_RGB",
            "color": {"red": 10, "green": 20, "blue": 30},
        }
    )
    client = SmartTubClient(SimpleNamespace())
    client._spas = [spa]

    await client.set_light_state(True, light_id="zone_2")
    assert spa.requests[-1] == (
        "PATCH",
        "lights/2",
        {"mode": "FULL_DYNAMIC_RGB", "red": 10, "green": 20, "blue": 30},
    )

    client._spas = [_FailingLightSpa()]
    with pytest.raises(CloudCommandError, match="light state"):
        await client.set_light_state(False, light_id="zone_2")


@pytest.mark.asyncio
async def test_light_color_success_and_cloud_failure():
    spa = _LightSpa()
    client = SmartTubClient(SimpleNamespace())
    client._spas = [spa]

    await client.set_light_color("#ff0080", light_id="zone_2")
    assert spa.requests == [
        (
            "PATCH",
            "lights/2",
            {"color": {"red": 255, "green": 0, "blue": 128}},
        )
    ]

    client._spas = [_FailingLightSpa()]
    with pytest.raises(CloudCommandError, match="RGB color"):
        await client.set_light_color("1,2,3", light_id="zone_2")


@pytest.mark.asyncio
async def test_light_brightness_scales_rgb_and_reports_read_failure():
    spa = _RawLightSpa(
        {
            "zone": 2,
            "mode": "FULL_DYNAMIC_RGB",
            "color": {"red": 85, "green": 42, "blue": 0},
        }
    )
    client = SmartTubClient(SimpleNamespace())
    client._spas = [spa]

    await client.set_light_brightness(50, light_id="zone_2")
    assert spa.requests[-1] == (
        "PATCH",
        "lights/2",
        {"color": {"red": 42, "green": 20, "blue": 0}},
    )

    client._spas = [_FailingLightSpa()]
    with pytest.raises(CloudCommandError, match="read light brightness"):
        await client.set_light_brightness(50, light_id="zone_2")


@pytest.mark.asyncio
async def test_pump_command_rejects_an_unknown_pump():
    client = SmartTubClient(SimpleNamespace())
    client._spas = [_PumpSpa()]

    with pytest.raises(ComponentNotFoundError, match="P9"):
        await client.set_pump_state(True, pump_id="P9")


@pytest.mark.asyncio
async def test_pump_command_propagates_cloud_failures():
    pump = _Pump("P1", ["OFF"], fail_toggle=True)
    client = SmartTubClient(SimpleNamespace())
    client._spas = [_PumpSpa([pump])]

    with pytest.raises(CloudCommandError, match="pump P1"):
        await client.set_pump_state(True, pump_id="P1")


@pytest.mark.asyncio
async def test_pump_toggle_readback_timeout_is_unknown_not_failed():
    pump = _Pump(
        "P1",
        ["OFF"],
        toggle_error=RuntimeError("State change not reflected within timeout period"),
    )
    client = SmartTubClient(SimpleNamespace())
    client._spas = [_PumpSpa([pump])]

    status = await client.set_pump_state(True, pump_id="P1")

    assert status is CommandStatus.UNKNOWN


@pytest.mark.asyncio
async def test_low_two_speed_pump_reaches_off_after_two_verified_toggles():
    pump = _Pump("P1", ["LOW", "HIGH", "OFF"])
    client = SmartTubClient(SimpleNamespace())
    client._spas = [_PumpSpa([pump])]

    status = await client.set_pump_state(False, pump_id="P1")

    assert status is CommandStatus.CONFIRMED
    assert pump.toggle_count == 2


@pytest.mark.asyncio
async def test_unknown_pump_state_is_not_toggled():
    pump = _Pump("P1", ["VENDOR_STATE"])
    client = SmartTubClient(SimpleNamespace())
    client._spas = [_PumpSpa([pump])]

    with pytest.raises(CommandVerificationError, match="unknown state"):
        await client.set_pump_state(False, pump_id="P1")

    assert pump.toggle_count == 0


@pytest.mark.asyncio
async def test_invalid_heat_mode_does_not_fall_back_to_auto():
    class Spa:
        class HeatMode:
            AUTO = object()

        async def set_heat_mode(self, _mode):
            raise AssertionError("invalid commands must not reach the cloud")

    client = SmartTubClient(SimpleNamespace())
    client._spas = [Spa()]

    with pytest.raises(UnsupportedCommandError, match="AUTOO"):
        await client.set_heat_mode("AUTOO")


def test_rgb_json_preserves_zero_channels():
    client = SmartTubClient(SimpleNamespace())

    assert client._parse_rgb_color('{"red":0,"green":255,"blue":0}') == (
        0,
        255,
        0,
    )
