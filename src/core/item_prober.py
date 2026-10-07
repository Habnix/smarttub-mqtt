from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from src.core.config_loader import AppConfig
from src.core.discovery_output import (
    DiscoveryFileRepository,
    DiscoveryMqttPublisher,
    DiscoveryPersistenceError,
)
from src.core.discovery_recovery import DiscoveryRecoveryJournal
from src.core.discovery_serialization import make_serializable
from src.core.light_discovery_engine import LightDiscoveryEngine
from src.core.light_mode_catalog import (
    LightModeTestStatus,
    available_light_mode_names,
    is_mode_detected,
)
from src.core.smarttub_gateway import SmartTubGateway

# Import ErrorTracker if available (T058)
try:
    from src.core.error_tracker import ErrorCategory, ErrorSeverity, ErrorTracker

    HAS_ERROR_TRACKER = True
except ImportError:
    HAS_ERROR_TRACKER = False
    ErrorTracker = None  # type: ignore
    ErrorCategory = None  # type: ignore
    ErrorSeverity = None  # type: ignore

# Import DiscoveryProgressTracker if available (T059)
try:
    from src.core.discovery_progress import (
        ComponentType,
        DiscoveryPhase,
        DiscoveryProgressTracker,
    )

    HAS_PROGRESS_TRACKER = True
except ImportError:
    HAS_PROGRESS_TRACKER = False
    DiscoveryProgressTracker = None  # type: ignore
    DiscoveryPhase = None  # type: ignore
    ComponentType = None  # type: ignore

logger = logging.getLogger(__name__)


class ItemProber:
    """Probes spas for available items (pumps, lights, heater) and records findings.

    Behaviour:
    - Calls read-only methods (get_status, get_pumps, get_lights) on spa objects.
    - Records discovered items and any non-fatal errors.
    - Writes a YAML file with discovered items under the configured config volume
      (fallback: ./config/discovered_items.yaml).
    - Publishes a JSON summary to MQTT under: {base_topic}/{spa_id}/discovery/result
    """

    # Brightness levels to test (0-100)
    BRIGHTNESS_LEVELS = (0, 25, 50, 75, 100)

    # Delay between light mode tests (seconds)
    LIGHT_TEST_DELAY_SECONDS = 0.25

    def __init__(
        self,
        config: AppConfig,
        smarttub_client: Any,
        topic_mapper: Any,
        *,
        error_tracker: Any | None = None,
        progress_tracker: Any | None = None,
        recovery_journal: DiscoveryRecoveryJournal | None = None,
        file_repository: DiscoveryFileRepository | None = None,
        mqtt_publisher: DiscoveryMqttPublisher | None = None,
    ):
        self.config = config
        self.smarttub_client = smarttub_client
        self.topic_mapper = topic_mapper
        self.error_tracker = error_tracker
        self.progress_tracker = progress_tracker
        self.gateway = getattr(smarttub_client, "gateway", SmartTubGateway())
        self.discovery_engine = LightDiscoveryEngine(
            config,
            gateway=self.gateway,
            recovery_journal=recovery_journal,
        )
        self.file_repository = file_repository or DiscoveryFileRepository()
        self.mqtt_publisher = mqtt_publisher or DiscoveryMqttPublisher(
            config, topic_mapper
        )

    async def probe_all(self) -> dict[str, Any]:
        """Probe every known spa, then persist and publish the results."""
        spas = list(self.smarttub_client.spas)
        await self.discovery_engine.recover_pending(spas)
        self._start_progress(len(spas))

        results: dict[str, Any] = {}
        for spa in spas:
            spa_id = str(getattr(spa, "id", "unknown"))
            results[spa_id] = await self._probe_spa_with_reporting(spa, spa_id)

        self._set_progress_phase(DiscoveryPhase.WRITING_YAML)
        await self._persist_and_publish(results)
        self._set_progress_phase(DiscoveryPhase.COMPLETED)
        return results

    def _start_progress(self, total_spas: int) -> None:
        if not (self.progress_tracker and HAS_PROGRESS_TRACKER):
            return
        self.progress_tracker.start_discovery(total_spas=total_spas)
        self.progress_tracker.set_overall_phase(DiscoveryPhase.FETCHING_SPAS)

    def _set_progress_phase(self, phase: Any) -> None:
        if self.progress_tracker and HAS_PROGRESS_TRACKER:
            self.progress_tracker.set_overall_phase(phase)

    async def _probe_spa_with_reporting(self, spa: Any, spa_id: str) -> dict[str, Any]:
        spa_name = getattr(spa, "brand", "Unknown Spa")
        if self.progress_tracker and HAS_PROGRESS_TRACKER:
            self.progress_tracker.start_spa(spa_id, spa_name)
            self.progress_tracker.set_overall_phase(DiscoveryPhase.PROBING_SPA)

        try:
            result = await self._probe_spa(spa)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error probing spa %s: %s", spa_id, exc)
            self._track_probe_error(spa_id, exc)
            if self.progress_tracker and HAS_PROGRESS_TRACKER:
                self.progress_tracker.complete_spa(spa_id, error=str(exc))
            return {
                "spa_id": spa_id,
                "discovered_at": datetime.now(UTC).isoformat(),
                "error": str(exc),
            }

        if self.progress_tracker and HAS_PROGRESS_TRACKER:
            self.progress_tracker.complete_spa(spa_id)
        return result

    def _track_probe_error(self, spa_id: str, error: Exception) -> None:
        if not (self.error_tracker and HAS_ERROR_TRACKER):
            return
        self.error_tracker.track_error(
            category=ErrorCategory.DISCOVERY,
            message=f"Failed to probe spa {spa_id}: {error!s}",
            severity=ErrorSeverity.ERROR,
            error_code="DISCOVERY_PROBE_FAILED",
            details={"spa_id": spa_id},
        )

    async def _persist_and_publish(self, results: dict[str, Any]) -> None:
        safe_results = {
            spa_id: self._make_serializable(payload)
            for spa_id, payload in results.items()
        }
        try:
            self.mqtt_publisher.publish_pump_metadata(safe_results)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to publish pump discovery metadata: %s", exc)

        try:
            await self.file_repository.save_async(safe_results)
        except DiscoveryPersistenceError as exc:
            logger.error("Failed to write discovered items YAML: %s", exc)
            self._track_persistence_error(exc)
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected discovery persistence failure: %s", exc)
            self._track_persistence_error(exc)

        try:
            self.mqtt_publisher.publish_results(safe_results)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to publish discovery results to MQTT: %s", exc)

    def _track_persistence_error(self, error: Exception) -> None:
        if not (self.error_tracker and HAS_ERROR_TRACKER):
            return
        self.error_tracker.track_error(
            category=ErrorCategory.YAML_PARSING,
            message=f"Discovery persistence failed: {error!s}",
            severity=ErrorSeverity.ERROR,
            error_code="YAML_WRITE_FAILED",
        )

    async def _probe_spa(self, spa: Any) -> dict[str, Any]:
        """Collect one spa inventory while keeping failures component-scoped."""
        spa_id = str(getattr(spa, "id", "unknown"))
        if self.progress_tracker and HAS_PROGRESS_TRACKER:
            self.progress_tracker.set_spa_component_count(spa_id, 5)

        result: dict[str, Any] = {
            "spa_id": spa_id,
            "discovered_at": datetime.now(UTC).isoformat(),
            "capabilities_python-smarttub": {},
            "spa": self._make_serializable(spa),
            "heater": {},
            "lights": [],
            "pumps": [],
            "errors": [],
            "capabilities": {},
        }

        await self._probe_status(spa, spa_id, result)
        for method_name, result_key, error_key in (
            ("get_status_full", "status_full", "status_full_error"),
            ("get_debug_status", "debug_status", "debug_status_error"),
            ("get_energy_usage", "energy_usage", "energy_usage_error"),
            ("get_errors", "errors_list", "errors_list_error"),
            ("get_reminders", "reminders", "reminders_error"),
        ):
            await self._probe_optional(
                spa, spa_id, result, method_name, result_key, error_key
            )

        self._probe_features(spa, result)
        result["pumps"] = await self._probe_pumps(spa, spa_id, result)
        lights, light_objects = await self._probe_lights(spa, spa_id, result)
        result["lights"] = lights
        self._add_upstream_capabilities(result)

        if getattr(self.config, "discovery_test_all_light_modes", False):
            await self._probe_light_modes(spa, spa_id, light_objects, result)

        if not result["errors"]:
            result.pop("errors", None)
        return result

    async def _probe_status(
        self, spa: Any, spa_id: str, result: dict[str, Any]
    ) -> None:
        if self.progress_tracker and HAS_PROGRESS_TRACKER:
            self.progress_tracker.start_component(
                spa_id, ComponentType.STATUS, "status"
            )
        try:
            status = await spa.get_status()
            water = getattr(status, "water", None)
            heater_present = getattr(status, "heater1Present", None)
            if heater_present is None:
                heater_present = water is not None
            result["heater"] = {
                "present": bool(heater_present),
                "water_temperature": (
                    getattr(water, "temperature", None)
                    if water is not None
                    else getattr(status, "water_temperature", None)
                ),
            }
        except Exception as exc:  # noqa: BLE001
            logger.debug("Status probe failed for spa %s: %s", spa_id, exc)
            self._append_probe_error(result, "status_error", exc)
            if self.progress_tracker and HAS_PROGRESS_TRACKER:
                self.progress_tracker.complete_component(
                    spa_id, "status", error=str(exc)
                )
            return

        if self.progress_tracker and HAS_PROGRESS_TRACKER:
            self.progress_tracker.complete_component(
                spa_id,
                "status",
                example_info={"water_temp": result["heater"].get("water_temperature")},
            )

    async def _probe_optional(
        self,
        spa: Any,
        spa_id: str,
        result: dict[str, Any],
        method_name: str,
        result_key: str,
        error_key: str,
    ) -> None:
        try:
            value = await getattr(spa, method_name)()
            result[result_key] = self._make_serializable(value)
        except Exception as exc:  # noqa: BLE001
            logger.debug("%s probe failed for spa %s: %s", result_key, spa_id, exc)
            self._append_probe_error(result, error_key, exc)

    @staticmethod
    def _append_probe_error(
        result: dict[str, Any], error_key: str, error: Exception
    ) -> None:
        result.setdefault("errors", []).append(f"{error_key}: {error!s}")

    @staticmethod
    def _probe_features(spa: Any, result: dict[str, Any]) -> None:
        result["features"] = {
            "clearray_available": callable(getattr(spa, "toggle_clearray", None))
        }

    async def _probe_pumps(
        self, spa: Any, spa_id: str, result: dict[str, Any]
    ) -> list[dict[str, Any]]:
        try:
            payload = await spa.get_pumps()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Pump probe failed for spa %s: %s", spa_id, exc)
            self._append_probe_error(result, "pumps_error", exc)
            return []
        return [
            self._pump_inventory_item(pump, spa_id)
            for pump in self._collection(payload, "pumps")
        ]

    def _pump_inventory_item(self, pump: Any, spa_id: str) -> dict[str, Any]:
        if isinstance(pump, dict):
            pump_id = pump.get("id") or pump.get("pumpId")
            pump_type = pump.get("type")
            supports = {
                "state": "state" in pump or "mode" in pump,
                "speed": "speed" in pump,
            }
        else:
            pump_id = getattr(pump, "id", None) or getattr(pump, "pumpId", None)
            pump_type = getattr(pump, "type", None)
            supports = {
                "state": hasattr(pump, "state") or hasattr(pump, "mode"),
                "speed": hasattr(pump, "speed"),
            }
        return {
            "id": pump_id,
            "type": pump_type,
            "raw": self._serialized_without_spa(pump),
            "supports": supports,
            "state_writetopic": (
                f"{self.config.mqtt.base_topic}/{spa_id}/pumps/"
                f"{pump_id}/state_writetopic"
            ),
        }

    async def _probe_lights(
        self, spa: Any, spa_id: str, result: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[Any]]:
        try:
            payload = await spa.get_lights()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Light probe failed for spa %s: %s", spa_id, exc)
            self._append_probe_error(result, "lights_error", exc)
            return [], []

        raw_lights = self._collection(payload, "lights")
        inventory = [self._light_inventory_item(light) for light in raw_lights]
        mutable_objects = [light for light in raw_lights if not isinstance(light, dict)]
        return inventory, mutable_objects

    def _light_inventory_item(self, light: Any) -> dict[str, Any]:
        if isinstance(light, dict):
            zone = light.get("zone")
            light_id = light.get("id") or f"zone_{zone}"
            color = light.get("color")
            cycle_speed = light.get("cycleSpeed", light.get("cycle_speed"))
            supports = {
                "color": color is not None,
                "brightness": "intensity" in light or "brightness" in light,
                "cycle_speed": cycle_speed is not None,
            }
        else:
            zone = getattr(light, "zone", None)
            zone_label = zone if zone is not None else "unknown"
            light_id = getattr(light, "id", None) or f"zone_{zone_label}"
            color = getattr(light, "color", None)
            cycle_speed = getattr(
                light, "cycleSpeed", getattr(light, "cycle_speed", None)
            )
            supports = {
                "color": color is not None,
                "brightness": hasattr(light, "intensity")
                or hasattr(light, "brightness"),
                "cycle_speed": cycle_speed is not None,
            }
        return {
            "id": light_id,
            "raw": self._serialized_without_spa(light),
            "cycle_speed": cycle_speed,
            "supports": supports,
            "detected_modes": [],
        }

    def _serialized_without_spa(self, value: Any) -> Any:
        serialized = self._make_serializable(value)
        if isinstance(serialized, dict):
            serialized.pop("spa", None)
        return serialized

    @staticmethod
    def _collection(payload: Any, key: str) -> list[Any]:
        if isinstance(payload, dict):
            items = payload.get(key, [])
            return items if isinstance(items, list) else []
        return payload if isinstance(payload, list) else []

    @staticmethod
    def _add_upstream_capabilities(result: dict[str, Any]) -> None:
        try:
            import smarttub  # type: ignore[import-untyped]

            capabilities = {
                "pump_states": [member.name for member in smarttub.SpaPump.PumpState],
                "pump_types": [member.name for member in smarttub.SpaPump.PumpType],
                "light_modes": [member.name for member in smarttub.SpaLight.LightMode],
                "primary_filtration_modes": [
                    member.name
                    for member in (
                        smarttub.SpaPrimaryFiltrationCycle.PrimaryFiltrationMode
                    )
                ],
                "light_cycle_speed": {
                    "supported": True,
                    "field": "cycleSpeed",
                    "read_only": True,
                },
                "light_intensity": {"min": 0, "max": 100, "example": 50},
            }
            result["capabilities_python-smarttub"].update(capabilities)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not introspect python-smarttub enums: %s", exc)

    async def _probe_light_modes(
        self,
        spa: Any,
        spa_id: str,
        light_objects: list[Any],
        result: dict[str, Any],
    ) -> None:
        try:
            status = await spa.get_status()
            online = getattr(status, "online", None)
            online_name = getattr(online, "name", online)
            if online_name == "OFFLINE" or online is False:
                logger.warning(
                    "Spa %s is offline; skipping light mode discovery", spa_id
                )
                return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not verify spa %s online status: %s", spa_id, exc)

        try:
            self.mqtt_publisher.publish_status(spa_id, "testing")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not publish discovery testing status: %s", exc)

        try:
            tests = []
            for light in light_objects:
                logger.info(
                    "Starting discovery for spa %s light zone %s",
                    spa_id,
                    getattr(light, "zone", None),
                )
                tests.append(await self._test_all_light_modes(spa, light, spa_id))
            if tests:
                result["capabilities"]["light_mode_tests"] = tests
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Systematic light mode testing failed for spa %s: %s", spa_id, exc
            )
            self._append_probe_error(result, "light_mode_tests_error", exc)
            return

        try:
            self.mqtt_publisher.publish_status(spa_id, "connected")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not publish discovery connected status: %s", exc)

    def _write_yaml(self, discovery_results: dict[str, Any]) -> None:
        """Compatibility wrapper around the extracted file repository."""
        self.file_repository.save(discovery_results)

    def _make_serializable(self, obj: Any) -> Any:
        """Compatibility wrapper for the extracted discovery serializer."""
        return make_serializable(obj)

    @staticmethod
    def _capture_light_state(light: Any) -> dict[str, Any] | None:
        """Compatibility wrapper around the shared discovery engine."""
        return LightDiscoveryEngine.capture_light_state(light)

    async def _restore_light_state_safely(
        self, light: Any, original_state: dict[str, Any] | None
    ) -> bool | None:
        """Compatibility wrapper around the shared discovery engine."""
        return await self.discovery_engine.restore_light_state(light, original_state)

    async def _test_all_light_modes(
        self, spa: Any, light_obj: Any, spa_id: str
    ) -> dict[str, Any]:
        """Run exhaustive mode testing through the shared safe transaction."""

        async def probe() -> dict[str, Any]:
            return await self._test_all_light_modes_impl(spa, light_obj, spa_id)

        result, restored = await self.discovery_engine.run_probe(
            spa_id, light_obj, probe
        )
        result["state_restored"] = restored
        return result

    async def _test_all_light_modes_impl(
        self, spa: Any, light_obj: Any, spa_id: str
    ) -> dict[str, Any]:
        """Execute the exhaustive CLI mode plan through small phases."""
        zone = int(getattr(light_obj, "zone", 0) or 0)
        result = self._new_light_mode_result(light_obj, zone)
        all_modes = available_light_mode_names()
        logger.info(
            "Starting exhaustive light mode testing for %s zone %s", spa_id, zone
        )

        candidates = await self._run_canonical_phase(
            spa, light_obj, spa_id, zone, all_modes, result
        )
        await self._run_brightness_phase(
            spa, light_obj, spa_id, zone, candidates, result
        )
        await self._add_rgb_capability(spa, spa_id, zone, result)
        result["unsupported_modes"] = [
            mode for mode in all_modes if mode not in result["supported_modes"]
        ]
        summary = result["test_summary"]
        logger.info(
            "Completed light mode testing for zone %s: %s/%s successful",
            zone,
            summary["successful_tests"],
            summary["total_tests"],
        )
        return result

    @staticmethod
    def _new_light_mode_result(light_obj: Any, zone: int) -> dict[str, Any]:
        zone_type = getattr(light_obj, "zone_type", None)
        return {
            "id": getattr(light_obj, "id", None) or f"zone_{zone}",
            "zone": zone,
            "zone_type": str(zone_type) if zone_type else None,
            "supported_modes": {},
            "unsupported_modes": [],
            "mode_results": {},
            "test_summary": {
                "total_tests": 0,
                "successful_tests": 0,
                "failed_tests": 0,
            },
        }

    async def _run_canonical_phase(
        self,
        spa: Any,
        light_obj: Any,
        spa_id: str,
        zone: int,
        modes: tuple[str, ...],
        result: dict[str, Any],
    ) -> list[str]:
        candidates = []
        for index, mode_name in enumerate(modes, 1):
            brightness = 0 if mode_name == "OFF" else 100
            self._publish_test_progress(
                spa_id,
                index,
                len(modes),
                f"Phase1: Testing zone {zone}: {mode_name} @ {brightness}%",
            )
            test_result = await self._test_light_mode(
                spa, light_obj, mode_name, brightness, zone, spa_id
            )
            result["mode_results"][mode_name] = test_result
            self._record_test_outcome(result, test_result)
            if is_mode_detected(test_result["status"]):
                candidates.append(mode_name)
            await asyncio.sleep(self.LIGHT_TEST_DELAY_SECONDS)
        return candidates

    async def _run_brightness_phase(
        self,
        spa: Any,
        light_obj: Any,
        spa_id: str,
        zone: int,
        candidates: list[str],
        result: dict[str, Any],
    ) -> None:
        levels = tuple(level for level in self.BRIGHTNESS_LEVELS if level != 100)
        total = sum(len(levels) for mode in candidates if mode != "OFF")
        current = 0
        for mode_name in candidates:
            mode_result: dict[str, Any] = {
                "brightness_support": [],
                "test_results": {},
                "rgb": None,
            }
            result["supported_modes"][mode_name] = mode_result
            if mode_name == "OFF":
                mode_result["brightness_support"].append(0)
                continue

            for brightness in levels:
                current += 1
                await self._test_brightness(
                    spa,
                    light_obj,
                    spa_id,
                    zone,
                    mode_name,
                    brightness,
                    current,
                    total,
                    mode_result,
                    result,
                )
            self._include_canonical_brightness(mode_name, mode_result, result)
            mode_result["brightness_support"] = sorted(
                set(mode_result["brightness_support"])
            )

    async def _test_brightness(
        self,
        spa: Any,
        light_obj: Any,
        spa_id: str,
        zone: int,
        mode_name: str,
        brightness: int,
        current: int,
        total: int,
        mode_result: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        self._publish_test_progress(
            spa_id,
            current,
            total,
            f"Phase2: Testing zone {zone}: {mode_name} @ {brightness}%",
        )
        test_result = await self._test_light_mode(
            spa, light_obj, mode_name, brightness, zone, spa_id
        )
        mode_result["test_results"][str(brightness)] = test_result
        if test_result["status"] == LightModeTestStatus.SUPPORTED.value:
            mode_result["brightness_support"].append(brightness)
            if mode_name == "WHITE" and mode_result["rgb"] is None:
                mode_result["rgb"] = await self._read_light_rgb(spa, zone)
        self._record_test_outcome(result, test_result)
        await asyncio.sleep(self.LIGHT_TEST_DELAY_SECONDS)

    def _publish_test_progress(
        self, spa_id: str, current: int, total: int, detail: str
    ) -> None:
        try:
            self.mqtt_publisher.publish_progress(
                spa_id,
                current=current,
                total=total,
                detail=detail,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not publish discovery progress: %s", exc)

    @staticmethod
    def _record_test_outcome(
        result: dict[str, Any], test_result: dict[str, Any]
    ) -> None:
        summary = result["test_summary"]
        summary["total_tests"] += 1
        if is_mode_detected(test_result["status"]):
            summary["successful_tests"] += 1
        else:
            summary["failed_tests"] += 1

    @staticmethod
    def _include_canonical_brightness(
        mode_name: str,
        mode_result: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        canonical = result["mode_results"][mode_name]
        if (
            canonical["status"] == LightModeTestStatus.SUPPORTED.value
            and 100 not in mode_result["brightness_support"]
        ):
            mode_result["brightness_support"].append(100)

    @staticmethod
    async def _read_light_rgb(spa: Any, zone: int) -> dict[str, int] | None:
        try:
            lights = await spa.get_lights()
        except Exception:  # noqa: BLE001
            return None
        for light in lights or []:
            if getattr(light, "zone", None) == zone:
                return {
                    "red": getattr(light, "red", 0),
                    "green": getattr(light, "green", 0),
                    "blue": getattr(light, "blue", 0),
                    "white": getattr(light, "white", 0),
                }
        return None

    async def _add_rgb_capability(
        self,
        spa: Any,
        spa_id: str,
        zone: int,
        result: dict[str, Any],
    ) -> None:
        modes = result["supported_modes"]
        if "FULL_DYNAMIC_RGB" not in modes:
            return
        logger.info("Phase 3: Testing RGB color capabilities for zone %s", zone)
        rgb_result = await self._test_rgb_color_capability(spa, zone, spa_id)
        if rgb_result:
            modes["FULL_DYNAMIC_RGB"]["rgb_capability"] = rgb_result

    async def _test_rgb_color_capability(
        self, spa: Any, zone: int, spa_id: str
    ) -> dict[str, Any] | None:
        """Test four representative colors and require three verified results."""
        logger.info("Testing RGB color capability for spa %s zone %s", spa_id, zone)
        test_colors = (
            ("RED", {"red": 255, "green": 0, "blue": 0}),
            ("GREEN", {"red": 0, "green": 255, "blue": 0}),
            ("BLUE", {"red": 0, "green": 0, "blue": 255}),
            ("WHITE", {"red": 255, "green": 255, "blue": 255}),
        )
        results: dict[str, Any] = {
            "color_control_works": False,
            "max_rgb_value": 0,
            "tested_colors": {},
        }
        try:
            await self.gateway.patch_light(
                spa,
                zone,
                {"mode": "FULL_DYNAMIC_RGB"},
                timeout=self._command_timeout(),
            )
            await asyncio.sleep(5)
            for color_name, color_values in test_colors:
                outcome = await self._test_rgb_color(
                    spa, zone, color_name, color_values
                )
                results["tested_colors"][color_name] = outcome
                if outcome["success"]:
                    results["max_rgb_value"] = max(
                        results["max_rgb_value"], max(outcome["actual"].values())
                    )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to test RGB capability for zone %s: %s", zone, exc)
            return None

        successes = sum(
            1 for outcome in results["tested_colors"].values() if outcome["success"]
        )
        results["color_control_works"] = successes >= 3
        logger.info(
            "RGB color capability for zone %s: %s/4 verified",
            zone,
            successes,
        )
        return results

    async def _test_rgb_color(
        self,
        spa: Any,
        zone: int,
        color_name: str,
        requested: dict[str, int],
    ) -> dict[str, Any]:
        try:
            await self.gateway.patch_light(
                spa,
                zone,
                {"color": requested},
                timeout=self._command_timeout(),
            )
            await asyncio.sleep(5)
            lights = await asyncio.wait_for(
                spa.get_lights(), timeout=self._command_timeout()
            )
            actual = self._light_rgb_for_zone(lights, zone)
            success = actual is not None and self._rgb_matches(requested, actual)
            logger.debug(
                "Color test %s: requested=%s actual=%s", color_name, requested, actual
            )
            return {"requested": requested, "actual": actual, "success": success}
        except Exception as exc:  # noqa: BLE001
            logger.debug("Error testing color %s: %s", color_name, exc)
            return {"requested": requested, "error": str(exc), "success": False}

    @staticmethod
    def _light_rgb_for_zone(lights: Any, zone: int) -> dict[str, int] | None:
        for light in lights or []:
            if getattr(light, "zone", None) == zone:
                return {
                    "red": getattr(light, "red", 0),
                    "green": getattr(light, "green", 0),
                    "blue": getattr(light, "blue", 0),
                }
        return None

    @staticmethod
    def _rgb_matches(
        requested: dict[str, int], actual: dict[str, int], tolerance: int = 5
    ) -> bool:
        return all(
            abs(actual[channel] - requested[channel]) <= tolerance
            for channel in ("red", "green", "blue")
        )

    def _command_timeout(self) -> float:
        return max(
            5.0,
            float(
                getattr(
                    getattr(self.config, "safety", None),
                    "command_timeout_seconds",
                    10,
                )
            ),
        )

    async def _test_light_mode(
        self,
        spa: Any,
        light_obj: Any,
        mode_name: str,
        brightness: int,
        zone: int,
        spa_id: str,
    ) -> dict[str, Any]:
        """Test one mode through the shared discovery engine.

        The legacy context parameters stay in the signature temporarily so
        older adapters and characterization tests can migrate independently.
        """
        if getattr(light_obj, "spa", None) is None:
            light_obj.spa = spa
        if getattr(light_obj, "zone", None) != zone:
            return {
                "status": LightModeTestStatus.ERROR.value,
                "requested_intensity": brightness,
                "verified_intensity": None,
                "elapsed_ms": 0,
                "error": "light zone does not match requested zone",
            }
        return await self.discovery_engine.test_mode(
            light_obj,
            mode_name,
            wait_time=max(
                1.0,
                float(
                    getattr(
                        getattr(self.config, "safety", None),
                        "command_timeout_seconds",
                        10,
                    )
                ),
            ),
            intensity=brightness,
        )
