"""Shared, recovery-safe light discovery primitives.

This module owns every hardware-mutating light probe.  Callers are responsible
for selecting spas, modes and result formats, but not for mutation safety,
verification, retry classification or crash recovery.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, TypeVar

from src.core.discovery_recovery import DiscoveryRecoveryJournal
from src.core.light_mode_catalog import (
    LightModeTestStatus,
    available_light_mode_names,
    mode_is_mode_only,
    mode_uses_rgb_brightness,
)
from src.core.smarttub_gateway import SmartTubGateway

logger = logging.getLogger(__name__)

ProbeResult = TypeVar("ProbeResult")


class DiscoverySafetyError(RuntimeError):
    """Discovery cannot safely mutate hardware or recover a previous run."""


class LightDiscoveryEngine:
    """Execute light probes as journalled, verified transactions."""

    def __init__(
        self,
        config: Any,
        *,
        gateway: SmartTubGateway | None = None,
        recovery_journal: DiscoveryRecoveryJournal | None = None,
    ) -> None:
        self.config = config
        self.gateway = gateway or SmartTubGateway()
        self.recovery_journal = recovery_journal or DiscoveryRecoveryJournal()

    @staticmethod
    def capture_light_state(light: Any) -> dict[str, Any] | None:
        """Capture the complete state required for a verified restore."""
        mode = getattr(light, "mode", None)
        mode_name = getattr(mode, "name", mode)
        intensity = getattr(light, "intensity", None)
        if not mode_name or intensity is None:
            logger.warning(
                "Could not capture complete state for light zone %s",
                getattr(light, "zone", "?"),
            )
            return None

        state: dict[str, Any] = {"mode": str(mode_name), "intensity": intensity}
        color = {
            key: getattr(light, key, None) for key in ("red", "green", "blue", "white")
        }
        if all(value is not None for value in color.values()):
            state["color"] = color
        cycle_speed = getattr(light, "cycleSpeed", None)
        if cycle_speed is not None:
            state["cycleSpeed"] = cycle_speed
        return state

    async def run_probe(
        self,
        spa_id: str,
        light: Any,
        probe: Callable[[], Awaitable[ProbeResult]],
    ) -> tuple[ProbeResult, bool]:
        """Run a mutating probe and restore the original state even on cancel."""
        zone = getattr(light, "zone", None)
        if not isinstance(zone, int):
            raise DiscoverySafetyError("Light discovery requires a numeric zone")

        original_state = self.capture_light_state(light)
        if original_state is None:
            raise DiscoverySafetyError(
                f"Light zone {zone} cannot be probed because its state is incomplete"
            )

        await self.recovery_journal.record_async(str(spa_id), zone, original_state)
        try:
            result = await probe()
        except BaseException as probe_error:
            restored = await self.restore_and_clear(str(spa_id), light, original_state)
            if restored is not True:
                raise DiscoverySafetyError(
                    f"Could not verify recovery for {spa_id}/zone_{zone}"
                ) from probe_error
            raise

        restored = await self.restore_and_clear(str(spa_id), light, original_state)
        if restored is not True:
            raise DiscoverySafetyError(
                f"Could not verify recovery for {spa_id}/zone_{zone}"
            )
        return result, True

    async def restore_and_clear(
        self,
        spa_id: str,
        light: Any,
        original_state: dict[str, Any] | None,
    ) -> bool | None:
        """Shield restoration and clear the journal only after verification."""
        restore_task = asyncio.create_task(
            self.restore_light_state(light, original_state)
        )
        try:
            restored = await asyncio.shield(restore_task)
        except asyncio.CancelledError:
            restored = await restore_task
            if restored:
                await self.recovery_journal.clear_async(spa_id, int(light.zone))
            raise
        if restored:
            await self.recovery_journal.clear_async(spa_id, int(light.zone))
        return restored

    async def recover_pending(self, spas: Iterable[Any]) -> None:
        """Restore every journalled light before allowing another discovery."""
        available_spas = list(spas)
        for entry in await self.recovery_journal.entries_async():
            spa_id = str(entry.get("spa_id"))
            zone = entry.get("zone")
            original_state = entry.get("original_state")
            if not isinstance(zone, int) or not isinstance(original_state, dict):
                raise DiscoverySafetyError("Invalid discovery recovery journal entry")
            spa = next(
                (
                    candidate
                    for candidate in available_spas
                    if str(getattr(candidate, "id", "")) == spa_id
                ),
                None,
            )
            if spa is None:
                raise DiscoverySafetyError(f"Spa {spa_id} for recovery is unavailable")
            lights = await spa.get_lights()
            light = next(
                (item for item in lights if getattr(item, "zone", None) == zone),
                None,
            )
            if light is None:
                raise DiscoverySafetyError(
                    f"Light zone {zone} for recovery is unavailable"
                )
            restored = await self.restore_light_state(light, original_state)
            if restored is not True:
                raise DiscoverySafetyError(
                    f"Could not verify recovery for {spa_id}/zone_{zone}"
                )
            await self.recovery_journal.clear_async(spa_id, zone)

    async def restore_light_state(
        self, light: Any, original_state: dict[str, Any] | None
    ) -> bool | None:
        """Restore and read back a light without masking the probe outcome."""
        if not original_state:
            return None

        zone = getattr(light, "zone", None)
        if not isinstance(zone, int):
            logger.error("Cannot restore light without a numeric zone")
            return False
        body = {
            "mode": original_state["mode"],
            "intensity": original_state["intensity"],
        }
        for key in ("color", "cycleSpeed"):
            if key in original_state:
                body[key] = original_state[key]

        timeout = max(
            5.0,
            float(
                getattr(
                    getattr(self.config, "safety", None),
                    "command_timeout_seconds",
                    10,
                )
            ),
        )
        try:
            await asyncio.wait_for(
                self.gateway.patch_light(light.spa, zone, body), timeout=timeout
            )
            lights = await asyncio.wait_for(light.spa.get_lights(), timeout=timeout)
            restored = next(
                (item for item in lights if getattr(item, "zone", None) == zone),
                None,
            )
            restored_mode_value = getattr(restored, "mode", None)
            restored_mode = getattr(restored_mode_value, "name", restored_mode_value)
            restored_intensity = getattr(restored, "intensity", None)
            if (
                restored_mode != original_state["mode"]
                or restored_intensity != original_state["intensity"]
            ):
                raise RuntimeError(
                    f"verified {restored_mode}@{restored_intensity}, expected "
                    f"{original_state['mode']}@{original_state['intensity']}"
                )
            logger.info("Restored and verified original light state for zone %s", zone)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to restore original light state for zone %s: %s", zone, exc
            )
            return False

    @staticmethod
    def _mode_result(
        mode_name: str,
        status: LightModeTestStatus,
        started: float,
        requested_intensity: int,
        verified_intensity: int | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": status.value,
            "requested_intensity": requested_intensity,
            "verified_intensity": verified_intensity,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
        if error:
            result["error"] = error[:200]
        logger.debug("Light mode %s result: %s", mode_name, result)
        return result

    async def test_mode(
        self,
        light: Any,
        mode_name: str,
        *,
        wait_time: float,
        intensity: int | None = None,
    ) -> dict[str, Any]:
        """Set and verify one mode within a bounded time budget."""
        started = time.monotonic()
        requested_intensity = (
            intensity if intensity is not None else (0 if mode_name == "OFF" else 50)
        )

        try:
            known_mode = mode_name in available_light_mode_names()
        except Exception as exc:  # noqa: BLE001
            return self._mode_result(
                mode_name,
                LightModeTestStatus.ERROR,
                started,
                requested_intensity,
                error=str(exc),
            )
        if not known_mode:
            return self._mode_result(
                mode_name,
                LightModeTestStatus.API_REJECTED,
                started,
                requested_intensity,
                error="unknown mode",
            )

        body: dict[str, Any] = {"mode": mode_name}
        if mode_name == "OFF":
            body["intensity"] = 0
        elif not mode_is_mode_only(mode_name):
            body["intensity"] = requested_intensity
        if mode_uses_rgb_brightness(mode_name):
            body["color"] = {"red": 42, "green": 42, "blue": 42}

        command_timeout = max(
            5.0,
            float(
                getattr(
                    getattr(self.config, "safety", None),
                    "command_timeout_seconds",
                    10,
                )
            ),
        )
        try:
            for attempt in range(2):
                try:
                    await self.gateway.patch_light(
                        light.spa,
                        light.zone,
                        body,
                        timeout=command_timeout,
                    )
                    break
                except Exception as exc:  # noqa: BLE001
                    error = str(exc)
                    if "429" not in error and "Too Many Requests" not in error:
                        status = (
                            LightModeTestStatus.API_REJECTED
                            if "400" in error or "404" in error
                            else LightModeTestStatus.ERROR
                        )
                        return self._mode_result(
                            mode_name,
                            status,
                            started,
                            requested_intensity,
                            error=error,
                        )
                    if attempt == 1:
                        return self._mode_result(
                            mode_name,
                            LightModeTestStatus.ERROR,
                            started,
                            requested_intensity,
                            error=error,
                        )
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Light mode probe cancelled: %s", mode_name)
            raise

        deadline = time.monotonic() + max(1.0, wait_time)
        last_error: str | None = None
        while time.monotonic() < deadline:
            try:
                status = await light.spa.get_status_full()
                for status_light in getattr(status, "lights", None) or []:
                    if getattr(status_light, "zone", None) != light.zone:
                        continue
                    current_mode = getattr(status_light, "mode", None)
                    current_mode_name = getattr(current_mode, "name", current_mode)
                    current_intensity = getattr(status_light, "intensity", None)
                    if current_mode_name == mode_name:
                        if mode_is_mode_only(mode_name):
                            result_status = LightModeTestStatus.MODE_ONLY
                        elif current_intensity == requested_intensity:
                            result_status = LightModeTestStatus.SUPPORTED
                        elif current_intensity is None:
                            result_status = LightModeTestStatus.MODE_ONLY
                        else:
                            result_status = LightModeTestStatus.BRIGHTNESS_UNSUPPORTED
                        return self._mode_result(
                            mode_name,
                            result_status,
                            started,
                            requested_intensity,
                            current_intensity,
                        )
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
            await asyncio.sleep(min(1.0, max(0.05, deadline - time.monotonic())))

        return self._mode_result(
            mode_name,
            LightModeTestStatus.TIMEOUT,
            started,
            requested_intensity,
            error=last_error or "state change not verified before deadline",
        )
