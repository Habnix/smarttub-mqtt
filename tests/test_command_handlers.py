"""Regression tests for command validation before SmartTub cloud calls."""

from types import SimpleNamespace

import pytest

from src.core.command_models import CommandStatus, CommandValidationError
from src.mqtt.command_handlers import CommandHandlers


@pytest.mark.asyncio
async def test_brightness_zero_is_forwarded_without_truthiness_loss():
    calls = []
    updates = []

    async def set_light_brightness(value, light_id=None):
        calls.append((value, light_id))

    async def trigger_update():
        updates.append(True)

    handlers = CommandHandlers(
        SimpleNamespace(set_light_brightness=set_light_brightness), trigger_update
    )

    status = await handlers.set_light_brightness(
        {"brightness": 0, "light_id": "zone_1"}
    )

    assert calls == [(0, "zone_1")]
    assert updates == [True]
    assert status.value == "sent"


@pytest.mark.asyncio
async def test_invalid_pump_state_is_a_failed_command_not_a_logged_success():
    async def trigger_update():
        raise AssertionError("invalid command must not trigger a state update")

    handlers = CommandHandlers(SimpleNamespace(), trigger_update)

    with pytest.raises(CommandValidationError, match="pump state"):
        await handlers.set_pump_state({"state": "maybe", "pump_id": "P1"})


@pytest.mark.asyncio
async def test_verified_pump_readback_is_exposed_as_confirmed():
    updates = []

    async def set_pump_state(enabled, pump_id=None):
        assert (enabled, pump_id) == (False, "P1")
        return CommandStatus.CONFIRMED

    async def trigger_update():
        updates.append(True)

    handlers = CommandHandlers(
        SimpleNamespace(set_pump_state=set_pump_state), trigger_update
    )

    status = await handlers.set_pump_state({"state": "off", "pump_id": "P1"})

    assert status is CommandStatus.CONFIRMED
    assert updates == [True]


@pytest.mark.asyncio
async def test_unverified_temperature_readback_is_exposed_as_unknown():
    updates = []

    async def set_temperature(value):
        assert value == 26.0
        return CommandStatus.UNKNOWN

    async def trigger_update():
        updates.append(True)

    handlers = CommandHandlers(
        SimpleNamespace(set_temperature=set_temperature), trigger_update
    )

    status = await handlers.set_temperature({"temperature": 26})

    assert status is CommandStatus.UNKNOWN
    assert updates == [True]


@pytest.mark.asyncio
async def test_light_commands_require_an_explicit_component_id():
    async def trigger_update():
        raise AssertionError("invalid command must not trigger a state update")

    handlers = CommandHandlers(SimpleNamespace(), trigger_update)

    with pytest.raises(CommandValidationError, match="light_id"):
        await handlers.set_light_brightness({"brightness": 50})
