"""Integration tests for CommandManager command dispatch."""

import asyncio
from contextlib import suppress
from types import SimpleNamespace
from typing import ClassVar

import pytest

from src.core.command_models import CommandQueueFullError
from src.mqtt.command_manager import CommandManager


def test_dispatches_per_pump_command_to_registered_handler():
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id="spa-test"),
    )
    smarttub_client = SimpleNamespace(spas=[object()])
    manager = CommandManager(config, smarttub_client, mqtt_client=None)

    manager._handle_command_message(
        "smarttub-mqtt/spa-test/pumps/P1/state_writetopic", "on"
    )

    handler, data, _completion, command_path, command_id = (
        manager._command_queue.get_nowait()
    )
    assert handler == manager._handle_set_pump_state
    assert data == {"state": "on", "pump_id": "P1"}
    assert command_path == "pumps/P1/state_writetopic"
    assert command_id


def test_dispatches_per_light_brightness_command_to_registered_handler():
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id="spa-test"),
    )
    smarttub_client = SimpleNamespace(spas=[object()])
    manager = CommandManager(config, smarttub_client, mqtt_client=None)

    manager._handle_command_message(
        "smarttub-mqtt/spa-test/lights/zone_1/brightness_writetopic", "50"
    )

    handler, data, _completion, command_path, command_id = (
        manager._command_queue.get_nowait()
    )
    assert handler == manager._handle_set_light_brightness
    assert data == {"brightness": 50, "light_id": "zone_1"}
    assert command_path == "lights/zone_1/brightness_writetopic"
    assert command_id


def test_ignores_command_for_another_spa():
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id="spa-selected"),
    )
    smarttub_client = SimpleNamespace(spas=[object()])
    manager = CommandManager(config, smarttub_client, mqtt_client=None)

    manager._handle_command_message(
        "smarttub-mqtt/spa-other/pumps/P1/state_writetopic", "on"
    )

    assert manager._command_queue.empty()


def test_invalid_mqtt_temperature_reports_the_same_domain_error_code():
    published = []

    class MQTTClient:
        @staticmethod
        def publish_sync(topic, payload, qos=None, retain=None):
            published.append((topic, payload, qos, retain))

    detector = SimpleNamespace(
        get_cached_capabilities=lambda _spa_id: SimpleNamespace(
            heater_temperature_range={"min": 20.0, "max": 40.0}
        )
    )
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id="spa-test"),
    )
    manager = CommandManager(
        config,
        SimpleNamespace(spas=[object()]),
        MQTTClient(),
        capability_detector=detector,
    )

    manager._handle_command_message(
        "smarttub-mqtt/spa-test/heater/target_temperature_writetopic", "40.5"
    )

    assert manager._command_queue.empty()
    assert manager.get_command_history()[0]["error_code"] == "validation_error"
    assert published[-1][1]["error_code"] == "validation_error"


@pytest.mark.asyncio
async def test_subscribes_only_to_the_configured_spa():
    subscriptions = []

    async def subscribe(topic, callback):
        subscriptions.append((topic, callback))

    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id="spa-selected"),
    )
    manager = CommandManager(
        config,
        smarttub_client=SimpleNamespace(spas=[object()]),
        mqtt_client=SimpleNamespace(subscribe=subscribe),
    )

    await manager.subscribe_commands()

    assert subscriptions
    assert all("smarttub-mqtt/spa-selected/" in topic for topic, _ in subscriptions)
    assert all(topic.split("/")[1] == "spa-selected" for topic, _ in subscriptions)


@pytest.mark.asyncio
async def test_missing_auto_detected_spa_uses_guarded_subscription_wildcard():
    subscriptions = []

    async def subscribe(topic, callback):
        subscriptions.append((topic, callback))

    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id=None),
    )
    manager = CommandManager(
        config,
        smarttub_client=SimpleNamespace(spas=[]),
        mqtt_client=SimpleNamespace(subscribe=subscribe),
    )

    await manager.subscribe_commands()

    assert subscriptions
    assert all(topic.startswith("smarttub-mqtt/+/") for topic, _ in subscriptions)


@pytest.mark.asyncio
async def test_command_queue_waits_for_a_command_before_starting_the_next_one():
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id="spa-selected"),
    )
    manager = CommandManager(
        config, smarttub_client=SimpleNamespace(spas=[object()]), mqtt_client=None
    )
    first_started = asyncio.Event()
    allow_first_to_finish = asyncio.Event()
    second_started = asyncio.Event()

    async def first_handler(_data):
        first_started.set()
        await allow_first_to_finish.wait()

    async def second_handler(_data):
        second_started.set()

    manager._command_queue.put_nowait((first_handler, None))
    manager._command_queue.put_nowait((second_handler, None))
    worker = asyncio.create_task(manager.process_command_queue())
    try:
        await asyncio.wait_for(first_started.wait(), timeout=1)
        await asyncio.sleep(0.15)
        assert not second_started.is_set()

        allow_first_to_finish.set()
        await asyncio.wait_for(second_started.wait(), timeout=1)
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


@pytest.mark.asyncio
async def test_web_commands_can_await_the_same_serialized_queue_as_mqtt():
    calls: list[float] = []

    class SmartTubClient:
        spas: ClassVar[list[object]] = [object()]

        async def set_temperature(self, temperature: float) -> None:
            calls.append(temperature)

    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(
            device_id="spa-selected", state_update_delay_seconds=0
        ),
    )
    manager = CommandManager(config, SmartTubClient(), mqtt_client=None)
    worker = asyncio.create_task(manager.process_command_queue())
    try:
        result = await manager.execute_command(
            "heater/target_temperature_writetopic", {"temperature": 37.5}
        )
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker

    assert calls == [37.5]
    assert result.status.value == "sent"
    history = manager.get_command_history()
    assert len(history) == 1
    assert history[0]["command"] == "heater/target_temperature_writetopic"
    assert history[0]["status"] == "sent"
    assert [transition["status"] for transition in history[0]["transitions"]] == [
        "accepted",
        "sent",
    ]


@pytest.mark.asyncio
async def test_failed_web_command_records_failed_transition_and_raises():
    class SmartTubClient:
        spas: ClassVar[list[object]] = [object()]

        @staticmethod
        async def set_temperature(_temperature: float) -> None:
            raise RuntimeError("cloud unavailable")

    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(
            device_id="spa-selected", state_update_delay_seconds=0
        ),
    )
    manager = CommandManager(config, SmartTubClient(), mqtt_client=None)
    worker = asyncio.create_task(manager.process_command_queue())
    try:
        with pytest.raises(RuntimeError, match="cloud unavailable"):
            await manager.execute_command(
                "heater/target_temperature_writetopic", {"temperature": 37.5}
            )
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker

    history = manager.get_command_history()
    assert len(history) == 1
    assert history[0]["status"] == "failed"
    assert history[0]["message"] == "Unexpected command failure"
    assert "cloud unavailable" not in str(history[0])
    assert [transition["status"] for transition in history[0]["transitions"]] == [
        "accepted",
        "failed",
    ]


@pytest.mark.asyncio
async def test_command_transitions_are_published_for_mqtt_consumers():
    published = []

    class MQTTClient:
        @staticmethod
        def publish_sync(topic, payload, qos=None, retain=None):
            published.append((topic, payload, qos, retain))

    class SmartTubClient:
        spas: ClassVar[list[object]] = [object()]

        @staticmethod
        async def set_temperature(_temperature: float) -> None:
            return None

    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(
            device_id="spa-selected", state_update_delay_seconds=0
        ),
    )
    manager = CommandManager(config, SmartTubClient(), mqtt_client=MQTTClient())
    worker = asyncio.create_task(manager.process_command_queue())
    try:
        result = await manager.execute_command(
            "heater/target_temperature_writetopic", {"temperature": 37.5}
        )
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker

    assert [item[1]["status"] for item in published] == ["accepted", "sent"]
    assert all(
        item[0] == "smarttub-mqtt/spa-selected/commands/result" for item in published
    )
    assert all(item[1]["command_id"] == result.command_id for item in published)
    assert all(item[2:] == (1, False) for item in published)


@pytest.mark.asyncio
async def test_web_command_queue_rejects_overflow_without_waiting_forever():
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id="spa-selected"),
        safety=SimpleNamespace(command_queue_size=1, command_timeout_seconds=30),
    )
    manager = CommandManager(
        config, smarttub_client=SimpleNamespace(spas=[object()]), mqtt_client=None
    )
    manager._command_queue.put_nowait((manager._handle_set_temperature, {}, None))

    with pytest.raises(CommandQueueFullError, match="queue is full"):
        await manager.execute_command(
            "heater/target_temperature_writetopic", {"temperature": 37.5}
        )

    assert manager.get_command_history()[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_command_timeout_is_reported_and_releases_the_worker():
    class SmartTubClient:
        spas: ClassVar[list[object]] = [object()]

        @staticmethod
        async def set_temperature(_temperature):
            await asyncio.Event().wait()

    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(
            device_id="spa-selected", state_update_delay_seconds=0
        ),
        safety=SimpleNamespace(command_queue_size=2, command_timeout_seconds=0.01),
    )
    manager = CommandManager(config, SmartTubClient(), mqtt_client=None)
    worker = asyncio.create_task(manager.process_command_queue())
    try:
        with pytest.raises(Exception, match="execution timeout"):
            await manager.execute_command(
                "heater/target_temperature_writetopic", {"temperature": 37.5}
            )
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker

    assert manager.get_command_history()[0]["status"] == "failed"
    assert manager.get_command_history()[0]["message"] == "Command timed out"


@pytest.mark.asyncio
async def test_command_worker_reports_its_actual_lifecycle():
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub-mqtt"),
        smarttub=SimpleNamespace(device_id="spa-selected"),
        safety=SimpleNamespace(command_queue_size=2, command_timeout_seconds=1),
    )
    manager = CommandManager(
        config, smarttub_client=SimpleNamespace(spas=[]), mqtt_client=None
    )
    assert manager.is_worker_running is False

    worker = asyncio.create_task(manager.process_command_queue())
    await asyncio.sleep(0)
    assert manager.is_worker_running is True

    worker.cancel()
    with suppress(asyncio.CancelledError):
        await worker
    assert manager.is_worker_running is False
