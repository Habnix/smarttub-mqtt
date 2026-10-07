"""Characterization tests for the application's service lifecycle."""

import asyncio
from types import SimpleNamespace

import pytest

from src.cli import run


def test_broad_web_binding_without_auth_emits_security_warning(monkeypatch):
    warnings = []
    monkeypatch.setattr(
        run,
        "logger",
        SimpleNamespace(
            warning=lambda message, **context: warnings.append((message, context))
        ),
    )
    config = SimpleNamespace(
        web=SimpleNamespace(host="0.0.0.0", port=8080, auth_enabled=False)
    )

    run._warn_if_unprotected_web_binding(config)

    assert "trusted home network" in warnings[0][0]
    assert "never expose this port" in warnings[0][0]
    assert warnings[0][1]["extra"]["event"] == "web-ui-unprotected-network-binding"


def test_loopback_or_authenticated_web_binding_needs_no_warning(monkeypatch):
    warnings = []
    monkeypatch.setattr(
        run,
        "logger",
        SimpleNamespace(
            warning=lambda *args, **kwargs: warnings.append((args, kwargs))
        ),
    )
    run._warn_if_unprotected_web_binding(
        SimpleNamespace(
            web=SimpleNamespace(host="127.0.0.1", port=8080, auth_enabled=False)
        )
    )
    run._warn_if_unprotected_web_binding(
        SimpleNamespace(
            web=SimpleNamespace(host="0.0.0.0", port=8080, auth_enabled=True)
        )
    )

    assert warnings == []


def _runtime(events: list[str], config: SimpleNamespace) -> SimpleNamespace:
    class Broker:
        async def publish(self, _topic, payload, retain=False) -> None:
            assert retain is True
            events.append(f"status:{payload}")

    class CommandManager:
        def set_event_loop(self, _loop) -> None:
            events.append("set-event-loop")

        def set_state_manager(self, _state_manager) -> None:
            events.append("set-state-manager")

        async def subscribe_commands(self) -> None:
            events.append("subscribe-commands")

    return SimpleNamespace(
        config=config,
        error_tracker=SimpleNamespace(),
        broker=Broker(),
        smarttub_client=SimpleNamespace(),
        topic_mapper=SimpleNamespace(),
        state_manager=SimpleNamespace(),
        capability_detector=SimpleNamespace(),
        command_manager=CommandManager(),
    )


def _config(check_smarttub: bool) -> SimpleNamespace:
    return SimpleNamespace(
        check_smarttub=check_smarttub,
        mqtt=SimpleNamespace(base_topic="smarttub"),
        web=SimpleNamespace(enabled=False),
    )


@pytest.mark.asyncio
async def test_runtime_keeps_starting_when_mqtt_and_cloud_are_initially_down(
    monkeypatch,
):
    events = []
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub"),
        safety=SimpleNamespace(command_queue_size=10),
        capability=SimpleNamespace(
            cache_expiry_seconds=60, refresh_interval_seconds=300
        ),
    )

    class Broker:
        is_connected = False

        def __init__(self, *_args, **_kwargs):
            pass

        async def connect(self, *, allow_degraded=False):
            events.append(("broker-connect", allow_degraded))

        def publish_sync(self, topic, payload, qos=None, retain=None):
            events.append(("buffered", topic, payload, qos, retain))

    class SmartTub:
        is_connected = False

        def __init__(self, _config):
            self.spas = []

        async def initialize(self):
            raise ConnectionError("cloud unavailable")

    monkeypatch.setattr(run, "MQTTBrokerClient", Broker)
    monkeypatch.setattr(run, "SmartTubClient", SmartTub)
    monkeypatch.setattr(run, "configure_log_bridge", lambda *_args: None)
    monkeypatch.setattr(run, "MQTTTopicMapper", lambda *_args: SimpleNamespace())
    monkeypatch.setattr(run, "StateManager", lambda *_args: SimpleNamespace())
    monkeypatch.setattr(run, "CapabilityDetector", lambda *_args: SimpleNamespace())
    monkeypatch.setattr(run, "CommandManager", lambda *_args: SimpleNamespace())

    runtime = await run._initialize_runtime(config)

    assert runtime.broker.is_connected is False
    assert runtime.smarttub_client.is_connected is False
    assert events == [
        ("broker-connect", True),
        ("buffered", "smarttub/status", "starting", 1, True),
    ]


def test_background_tasks_use_the_configured_capability_interval(monkeypatch):
    created = []

    class Loop:
        @staticmethod
        def create_task(work):
            created.append(work)
            return work

    monkeypatch.setattr(run, "_polling_loop", lambda *args: ("poll", args))
    monkeypatch.setattr(
        run, "_capability_refresh_loop", lambda *args: ("capability", args)
    )
    command_manager = SimpleNamespace(process_command_queue=lambda: ("commands", ()))
    config = SimpleNamespace(
        check_smarttub=True,
        smarttub=SimpleNamespace(polling_interval_seconds=30),
        capability=SimpleNamespace(refresh_interval_seconds=347),
        mqtt=SimpleNamespace(base_topic="smarttub"),
    )

    run._start_background_tasks(
        config,
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(),
        command_manager,
        asyncio.Event(),
        Loop(),
    )

    capability_work = next(item for item in created if item[0] == "capability")
    assert capability_work[1][1] == 347


@pytest.mark.asyncio
async def test_regular_lifecycle_initializes_services_before_starting_workers(
    monkeypatch,
):
    events: list[str] = []
    shutdown_discovery_runtimes: list[object | None] = []
    config = _config(check_smarttub=True)
    runtime = _runtime(events, config)
    shutdown_event = asyncio.Event()
    shutdown_event.set()

    monkeypatch.setattr(run.config_loader, "load_config", lambda _path: config)

    async def initialize(_config):
        events.append("initialize")
        return runtime

    async def detect(_runtime):
        events.append("detect-capabilities")

    class DiscoveryRuntime:
        coordinator = "coordinator"

        def __init__(self, **_kwargs) -> None:
            events.append("create-discovery-runtime")

        async def start(self) -> None:
            events.append("start-discovery-runtime")

    async def shutdown(*args) -> None:
        shutdown_discovery_runtimes.append(args[-1])
        events.append("shutdown")

    monkeypatch.setattr(run, "_initialize_runtime", initialize)
    monkeypatch.setattr(
        run, "_publish_initial_metadata", lambda _runtime: events.append("metadata")
    )
    monkeypatch.setattr(run, "_detect_initial_capabilities", detect)
    monkeypatch.setattr(run, "DiscoveryRuntime", DiscoveryRuntime)
    monkeypatch.setattr(
        run, "_start_web_ui", lambda *_args: events.append("start-web-ui") or None
    )
    monkeypatch.setattr(
        run,
        "_start_background_tasks",
        lambda *_args: events.append("start-workers") or run._BackgroundTasks(),
    )
    monkeypatch.setattr(run, "_shutdown_runtime", shutdown)

    assert (
        await run._async_main(
            shutdown_event=shutdown_event, register_signal_handlers=False
        )
        == 0
    )
    assert events == [
        "initialize",
        "metadata",
        "detect-capabilities",
        "create-discovery-runtime",
        "start-discovery-runtime",
        "status:connected",
        "set-event-loop",
        "set-state-manager",
        "subscribe-commands",
        "start-web-ui",
        "start-workers",
        "shutdown",
    ]
    assert len(shutdown_discovery_runtimes) == 1
    assert shutdown_discovery_runtimes[0] is not None


@pytest.mark.asyncio
async def test_disabled_smarttub_lifecycle_skips_discovery_and_still_accepts_commands(
    monkeypatch,
):
    events: list[str] = []
    shutdown_discovery_runtimes: list[object | None] = []
    config = _config(check_smarttub=False)
    runtime = _runtime(events, config)
    shutdown_event = asyncio.Event()
    shutdown_event.set()

    monkeypatch.setattr(run.config_loader, "load_config", lambda _path: config)

    async def initialize(_config):
        events.append("initialize")
        return runtime

    async def shutdown(*args) -> None:
        shutdown_discovery_runtimes.append(args[-1])
        events.append("shutdown")

    monkeypatch.setattr(run, "_initialize_runtime", initialize)
    monkeypatch.setattr(
        run, "_publish_initial_metadata", lambda _runtime: events.append("metadata")
    )
    monkeypatch.setattr(
        run,
        "DiscoveryRuntime",
        lambda **_kwargs: pytest.fail("Discovery must not start when disabled"),
    )
    monkeypatch.setattr(run, "_start_web_ui", lambda *_args: None)
    monkeypatch.setattr(
        run, "_start_background_tasks", lambda *_args: run._BackgroundTasks()
    )
    monkeypatch.setattr(run, "_shutdown_runtime", shutdown)

    assert (
        await run._async_main(
            shutdown_event=shutdown_event, register_signal_handlers=False
        )
        == 0
    )
    assert events == [
        "initialize",
        "metadata",
        "status:check_smarttub_disabled",
        "status:connected",
        "set-event-loop",
        "set-state-manager",
        "subscribe-commands",
        "shutdown",
    ]
    assert shutdown_discovery_runtimes == [None]
