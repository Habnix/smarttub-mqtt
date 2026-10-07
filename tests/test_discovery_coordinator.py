"""Tests for restoring persisted discovery state at coordinator startup."""

from types import SimpleNamespace

import pytest

from src.core.discovery_coordinator import DiscoveryCoordinator
from src.core.discovery_result_store import DiscoveryResultStore
from src.core.discovery_state import DiscoveryResults, DiscoveryState


class _Runner:
    def __init__(self, *, running=False, fail_start=False, fail_stop=False):
        self.running = running
        self.fail_start = fail_start
        self.fail_stop = fail_stop
        self.started_modes = []
        self.stop_calls = 0

    def is_running(self):
        return self.running

    async def start_discovery(self, mode):
        if self.fail_start:
            raise RuntimeError("start failed")
        self.started_modes.append(mode.value)
        self.running = True
        return {"success": True, "mode": mode.value}

    async def stop_discovery(self):
        if self.fail_stop:
            raise RuntimeError("stop failed")
        self.stop_calls += 1
        self.running = False
        return {"success": True}


def _coordinator():
    DiscoveryCoordinator._instance = None
    coordinator = DiscoveryCoordinator(
        smarttub_client=SimpleNamespace(spas=[]),
        config=SimpleNamespace(safety=SimpleNamespace(command_timeout_seconds=1)),
    )
    coordinator._persisted_state_loaded = True
    return coordinator


@pytest.mark.asyncio
async def test_coordinator_restores_last_completed_run_from_yaml(tmp_path):
    store = DiscoveryResultStore(tmp_path / "discovered_items.yaml")
    store.save_light_modes(
        {
            "spas": {
                "spa-one": {
                    "lights": [
                        {
                            "id": "zone_1",
                            "detected_modes": ["OFF", "WHITE"],
                            "mode_results": {"WHITE": {"status": "supported"}},
                            "state_restored": True,
                        }
                    ]
                }
            }
        },
        run_metadata={
            "mode": "quick",
            "started_at": "2026-08-22T05:00:00+00:00",
            "completed_at": "2026-08-22T05:01:00+00:00",
            "total_lights": 1,
            "total_modes_detected": 2,
        },
    )

    DiscoveryCoordinator._instance = None
    try:
        coordinator = DiscoveryCoordinator(
            smarttub_client=SimpleNamespace(spas=[]),
            config=SimpleNamespace(safety=SimpleNamespace(command_timeout_seconds=1)),
        )
        coordinator.runner.result_store = store

        status = await coordinator.get_status()

        assert status["status"] == "completed"
        assert status["mode"] == "quick"
        assert status["completed_at"] == "2026-08-22T05:01:00+00:00"
        assert status["results"]["total_modes_detected"] == 2
        assert (
            status["results"]["spas"]["spa-one"]["lights"][0]["mode_results"]["WHITE"][
                "status"
            ]
            == "supported"
        )
    finally:
        DiscoveryCoordinator._instance = None


@pytest.mark.asyncio
async def test_start_validates_mode_running_state_and_runner_failures():
    coordinator = _coordinator()
    try:
        assert (await coordinator.start_discovery("invalid"))["success"] is False

        coordinator.runner = _Runner(running=True)
        assert (await coordinator.start_discovery("quick"))["error"] == (
            "Discovery already running"
        )

        coordinator.runner = _Runner()
        result = await coordinator.start_discovery("full")
        assert result == {"success": True, "mode": "full"}
        assert coordinator.runner.started_modes == ["full"]

        coordinator.runner = _Runner(fail_start=True)
        result = await coordinator.start_discovery("yaml_only")
        assert result == {"success": False, "error": "start failed"}
    finally:
        DiscoveryCoordinator._instance = None


@pytest.mark.asyncio
async def test_stop_and_reset_respect_the_runner_lifecycle():
    coordinator = _coordinator()
    try:
        coordinator.runner = _Runner()
        assert (await coordinator.stop_discovery())["error"] == "No discovery running"

        coordinator.runner = _Runner(running=True)
        assert await coordinator.stop_discovery() == {"success": True}
        assert coordinator.runner.stop_calls == 1

        assert await coordinator.reset_state() == {
            "success": True,
            "message": "State reset to idle",
        }
        coordinator.runner = _Runner(running=True)
        assert (await coordinator.reset_state())["success"] is False
    finally:
        DiscoveryCoordinator._instance = None


@pytest.mark.asyncio
async def test_results_and_mqtt_publication_share_the_current_state():
    coordinator = _coordinator()
    publications = []

    async def publisher(state):
        publications.append(state)

    try:
        no_results = await coordinator.get_results()
        assert no_results["success"] is False

        state = await coordinator.state_manager.get_state()
        state.results = DiscoveryResults(
            spas={"spa-test": {"lights": []}}, total_lights=1
        )
        await coordinator.state_manager.update_state({"results": state.results})
        assert (await coordinator.get_results())["results"]["total_lights"] == 1

        await coordinator.publish_status_to_mqtt()
        assert publications == []
        coordinator.set_mqtt_publisher(publisher)
        await coordinator.publish_status_to_mqtt()
        await coordinator._on_state_change(DiscoveryState())
        assert len(publications) == 2
    finally:
        DiscoveryCoordinator._instance = None


@pytest.mark.asyncio
async def test_shutdown_stops_an_active_singleton_and_clears_it():
    coordinator = _coordinator()
    runner = _Runner(running=True)
    coordinator.runner = runner

    await DiscoveryCoordinator.shutdown()

    assert runner.stop_calls == 1
    assert DiscoveryCoordinator.get_instance() is None
