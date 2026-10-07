"""Tests for the single discovery startup policy."""

import asyncio
from types import SimpleNamespace
from typing import ClassVar

import pytest

from src.cli.run import _should_start_discovery_runtime
from src.core.discovery_runtime import DiscoveryRuntime


@pytest.mark.parametrize(
    ("check_smarttub", "discover", "show_discovery", "expected"),
    [
        (True, False, False, True),
        (False, False, False, False),
        (True, True, False, False),
        (True, False, True, False),
    ],
)
def test_discovery_runtime_only_starts_for_the_regular_enabled_application(
    check_smarttub, discover, show_discovery, expected
):
    config = SimpleNamespace(check_smarttub=check_smarttub)

    assert (
        _should_start_discovery_runtime(
            config, discover=discover, show_discovery=show_discovery
        )
        is expected
    )


class _Coordinator:
    started_modes: ClassVar[list[str]] = []

    def __init__(self, **_kwargs) -> None:
        pass

    async def start_discovery(self, mode: str) -> None:
        self.started_modes.append(mode)


class _DiscoveryHandler:
    def __init__(self, **_kwargs) -> None:
        pass

    async def start(self) -> None:
        pass


class _YAMLFallbackPublisher:
    def __init__(self, **_kwargs) -> None:
        pass

    async def publish_from_yaml(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_discovery_mode_off_does_not_start_probing(monkeypatch):
    import src.core.discovery_runtime as runtime_module

    _Coordinator.started_modes = []
    monkeypatch.setenv("DISCOVERY_MODE", "off")
    monkeypatch.setattr(runtime_module, "DiscoveryCoordinator", _Coordinator)
    monkeypatch.setattr(runtime_module, "DiscoveryMQTTHandler", _DiscoveryHandler)
    monkeypatch.setattr(runtime_module, "YAMLFallbackPublisher", _YAMLFallbackPublisher)

    runtime = DiscoveryRuntime(
        config=SimpleNamespace(),
        smarttub_client=SimpleNamespace(),
        topic_mapper=SimpleNamespace(),
        broker=SimpleNamespace(),
        error_tracker=SimpleNamespace(),
        event_loop=asyncio.get_running_loop(),
    )
    await runtime.start()

    assert _Coordinator.started_modes == []
