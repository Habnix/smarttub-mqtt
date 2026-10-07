"""Tests for shared light-mode discovery behaviour."""

from types import SimpleNamespace

import pytest

from src.core.background_discovery import BackgroundDiscoveryRunner
from src.core.discovery_recovery import DiscoveryRecoveryJournal
from src.core.discovery_state import DiscoveryStateManager
from src.core.item_prober import ItemProber
from src.core.light_discovery_engine import DiscoverySafetyError, LightDiscoveryEngine
from src.core.light_mode_catalog import (
    LightModeTestStatus,
    light_mode_catalog,
    light_modes_for_discovery,
)


class _FakeSpa:
    def __init__(self, status_light):
        self.status_light = status_light
        self.requests = []

    async def request(self, method, endpoint, body):
        self.requests.append((method, endpoint, body))

    async def get_status_full(self):
        return SimpleNamespace(lights=[self.status_light])

    async def get_lights(self):
        return [self.status_light]


def _runner():
    return BackgroundDiscoveryRunner(
        state_manager=DiscoveryStateManager(),
        smarttub_client=SimpleNamespace(spas=[]),
        config=SimpleNamespace(
            safety=SimpleNamespace(command_timeout_seconds=1),
        ),
    )


def test_catalogue_comes_from_python_smarttub_and_quick_is_a_subset():
    catalog = light_mode_catalog()

    assert len(catalog["all"]) == 18
    assert set(catalog["quick"]) == {"OFF", "ON", "PURPLE", "WHITE"}
    assert set(light_modes_for_discovery("quick")).issubset(catalog["all"])
    assert light_modes_for_discovery("full") == tuple(catalog["all"])


@pytest.mark.asyncio
async def test_background_probe_reports_brightness_mismatch_without_false_success():
    status_light = SimpleNamespace(
        zone=1,
        mode=SimpleNamespace(name="WHITE"),
        intensity=0,
    )
    spa = _FakeSpa(status_light)
    light = SimpleNamespace(zone=1, spa=spa)

    result = await _runner()._test_light_mode(light, "WHITE", wait_time=1)

    assert result["status"] == LightModeTestStatus.BRIGHTNESS_UNSUPPORTED.value
    assert result["requested_intensity"] == 50
    assert result["verified_intensity"] == 0


@pytest.mark.asyncio
async def test_background_probe_treats_wheel_modes_as_mode_only():
    status_light = SimpleNamespace(
        zone=1,
        mode=SimpleNamespace(name="HIGH_SPEED_WHEEL"),
        intensity=100,
    )
    spa = _FakeSpa(status_light)
    light = SimpleNamespace(zone=1, spa=spa)

    result = await _runner()._test_light_mode(light, "HIGH_SPEED_WHEEL", wait_time=1)

    assert result["status"] == LightModeTestStatus.MODE_ONLY.value
    assert spa.requests[0] == ("PATCH", "lights/1", {"mode": "HIGH_SPEED_WHEEL"})


@pytest.mark.asyncio
async def test_background_probe_uses_rgb_for_dynamic_rgb_mode():
    status_light = SimpleNamespace(
        zone=1,
        mode=SimpleNamespace(name="FULL_DYNAMIC_RGB"),
        intensity=0,
    )
    spa = _FakeSpa(status_light)
    light = SimpleNamespace(zone=1, spa=spa)

    result = await _runner()._test_light_mode(light, "FULL_DYNAMIC_RGB", wait_time=1)

    assert result["status"] == LightModeTestStatus.MODE_ONLY.value
    assert spa.requests[0] == (
        "PATCH",
        "lights/1",
        {
            "mode": "FULL_DYNAMIC_RGB",
            "color": {"red": 42, "green": 42, "blue": 42},
        },
    )


@pytest.mark.asyncio
async def test_background_probe_restores_original_state():
    original = SimpleNamespace(
        zone=1,
        mode=SimpleNamespace(name="WHITE"),
        intensity=25,
        red=1,
        green=2,
        blue=3,
        white=4,
        cycleSpeed=5,
    )
    spa = _FakeSpa(original)
    original.spa = spa
    runner = _runner()

    await runner._restore_light_state_safely(
        original, runner._capture_light_state(original)
    )

    assert spa.requests == [
        (
            "PATCH",
            "lights/1",
            {
                "mode": "WHITE",
                "intensity": 25,
                "color": {"red": 1, "green": 2, "blue": 3, "white": 4},
                "cycleSpeed": 5,
            },
        )
    ]


def test_recovery_journal_is_atomic_and_clears_only_the_target(tmp_path):
    path = tmp_path / "discovery_recovery.yaml"
    journal = DiscoveryRecoveryJournal(path)

    journal.record("spa-1", 1, {"mode": "WHITE", "intensity": 25})
    journal.record("spa-1", 2, {"mode": "OFF", "intensity": 0})

    assert len(journal.entries()) == 2
    assert not path.with_suffix(".yaml.tmp").exists()

    journal.clear("spa-1", 1)

    assert journal.entries() == [
        {
            "spa_id": "spa-1",
            "zone": 2,
            "original_state": {"mode": "OFF", "intensity": 0},
        }
    ]


@pytest.mark.asyncio
async def test_interrupted_discovery_is_restored_before_a_new_run(tmp_path):
    original = SimpleNamespace(
        zone=1,
        mode=SimpleNamespace(name="WHITE"),
        intensity=25,
    )
    spa = _FakeSpa(original)
    spa.id = "spa-1"
    original.spa = spa
    journal = DiscoveryRecoveryJournal(tmp_path / "recovery.yaml")
    journal.record("spa-1", 1, {"mode": "WHITE", "intensity": 25})
    runner = BackgroundDiscoveryRunner(
        state_manager=DiscoveryStateManager(),
        smarttub_client=SimpleNamespace(spas=[spa]),
        config=SimpleNamespace(
            safety=SimpleNamespace(command_timeout_seconds=1),
        ),
        recovery_journal=journal,
    )

    await runner._recover_pending_lights()

    assert journal.entries() == []
    assert spa.requests == [("PATCH", "lights/1", {"mode": "WHITE", "intensity": 25})]


@pytest.mark.asyncio
async def test_item_prober_restores_state_when_cancelled_or_failed(tmp_path):
    config = SimpleNamespace(safety=SimpleNamespace(command_timeout_seconds=1))
    journal = DiscoveryRecoveryJournal(tmp_path / "cli-recovery.yaml")
    prober = ItemProber(
        config,
        SimpleNamespace(spas=[]),
        SimpleNamespace(),
        recovery_journal=journal,
    )
    original = SimpleNamespace(
        zone=2,
        mode=SimpleNamespace(name="PURPLE"),
        intensity=50,
        red=0,
        green=0,
        blue=0,
        white=255,
        spa=None,
    )
    spa = _FakeSpa(original)
    original.spa = spa

    async def failing_impl(*_args):
        raise RuntimeError("probe failed")

    prober._test_all_light_modes_impl = failing_impl

    with pytest.raises(RuntimeError, match="probe failed"):
        await prober._test_all_light_modes(spa, original, "spa-1")

    assert spa.requests[0][0:2] == ("PATCH", "lights/2")
    assert spa.requests[0][2]["mode"] == "PURPLE"
    assert spa.requests[0][2]["intensity"] == 50
    assert journal.entries() == []


@pytest.mark.asyncio
async def test_shared_engine_refuses_to_mutate_without_recoverable_state(tmp_path):
    light = SimpleNamespace(zone=1, mode=None, intensity=None)
    called = False

    async def probe():
        nonlocal called
        called = True

    engine = LightDiscoveryEngine(
        SimpleNamespace(safety=SimpleNamespace(command_timeout_seconds=1)),
        recovery_journal=DiscoveryRecoveryJournal(tmp_path / "recovery.yaml"),
    )

    with pytest.raises(DiscoverySafetyError, match="state is incomplete"):
        await engine.run_probe("spa-1", light, probe)

    assert called is False
    assert engine.recovery_journal.entries() == []


@pytest.mark.asyncio
async def test_shared_engine_blocks_after_unverified_restore_and_keeps_journal(
    tmp_path,
):
    original = SimpleNamespace(
        zone=1,
        mode=SimpleNamespace(name="WHITE"),
        intensity=25,
        spa=None,
    )
    mismatched = SimpleNamespace(
        zone=1,
        mode=SimpleNamespace(name="OFF"),
        intensity=0,
    )
    spa = _FakeSpa(mismatched)
    original.spa = spa
    journal = DiscoveryRecoveryJournal(tmp_path / "recovery.yaml")
    engine = LightDiscoveryEngine(
        SimpleNamespace(safety=SimpleNamespace(command_timeout_seconds=1)),
        recovery_journal=journal,
    )

    async def probe():
        return {"ok": True}

    with pytest.raises(DiscoverySafetyError, match="Could not verify recovery"):
        await engine.run_probe("spa-1", original, probe)

    assert journal.entries()[0]["original_state"] == {
        "mode": "WHITE",
        "intensity": 25,
    }


@pytest.mark.asyncio
async def test_cli_prober_runs_recovery_preflight_before_probing(tmp_path):
    spa = SimpleNamespace(id="spa-1", brand="Test")
    config = SimpleNamespace(
        mqtt=SimpleNamespace(base_topic="smarttub"),
        safety=SimpleNamespace(command_timeout_seconds=1),
    )
    prober = ItemProber(
        config,
        SimpleNamespace(spas=[spa]),
        SimpleNamespace(),
        recovery_journal=DiscoveryRecoveryJournal(tmp_path / "recovery.yaml"),
    )
    events = []

    async def recover_pending(spas):
        events.append(("recover", list(spas)))

    async def probe_spa(candidate):
        events.append(("probe", candidate))
        return {
            "spa_id": "spa-1",
            "discovered_at": "2026-08-22T00:00:00+00:00",
            "pumps": [],
        }

    prober.discovery_engine.recover_pending = recover_pending
    prober._probe_spa = probe_spa

    async def save_results(_results):
        return None

    prober.file_repository.save_async = save_results

    await prober.probe_all()

    assert events == [("recover", [spa]), ("probe", spa)]
