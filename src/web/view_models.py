"""Template view-model builders for the single-Spa Web UI."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.core.capability_detector import CapabilityDetector
from src.core.config_loader import AppConfig
from src.core.discovery_repository import DiscoveryRepository
from src.core.state_manager import StateManager
from src.core.state_models import StateSnapshot
from src.core.version import get_version_info

logger = logging.getLogger(__name__)
DISCOVERY_REPOSITORY = DiscoveryRepository()

_EMPTY_CAPABILITY = {
    "supported_features": {
        "heater": False,
        "pump": False,
        "light": False,
        "filtration": False,
    },
    "lights": None,
    "filtration": None,
}


async def _load_discovered_items() -> dict[str, Any]:
    """Read persisted discovery data when it is available."""
    try:
        return await DISCOVERY_REPOSITORY.discovered_items_async()
    except Exception:
        logger.warning("Could not load discovered_items.yaml", exc_info=True)
        return {}


def _add_detected_light_modes(
    state: StateSnapshot, discovered_spa: dict[str, Any]
) -> None:
    """Expose persisted mode discoveries on the copied state snapshot."""
    discovered_lights = {
        str(light.get("id")): light
        for light in discovered_spa.get("lights", [])
        if isinstance(light, dict) and light.get("id") is not None
    }
    components = state.get("components", {})
    for light in components.get("lights", []):
        discovered_light = discovered_lights.get(str(light.get("id")), {})
        modes = discovered_light.get("detected_modes", [])
        if not isinstance(modes, list):
            modes = []
        normalized_modes = [
            str(mode).strip().upper() for mode in modes if str(mode).strip()
        ]
        if normalized_modes and "OFF" not in normalized_modes:
            normalized_modes.insert(0, "OFF")
        light["detected_modes"] = normalized_modes


def _sort_lights_for_display(state: StateSnapshot) -> None:
    """Keep every rendered light list in numeric zone order."""
    lights = state.get("components", {}).get("lights", [])
    lights.sort(
        key=lambda light: (
            int(light.get("zone", 0)) if str(light.get("zone", "")).isdigit() else 0,
            str(light.get("id", "")),
        )
    )


def _ensure_display_shape(state: StateSnapshot) -> None:
    """Add honest UI placeholders without turning them into telemetry."""
    components = state.setdefault("components", {})
    components.setdefault(
        "spa",
        {"state": "unknown", "water_temperature": None, "air_temperature": None},
    )
    components.setdefault(
        "heater",
        {"state": "unknown", "temperature": None, "target_temperature": None},
    )
    components.setdefault("pumps", [])
    components.setdefault("lights", [])


def _selected_capability(
    profiles: dict[str, Any], configured_spa_id: str | None
) -> tuple[str | None, dict[str, Any]]:
    """Return the profile represented by this single-Spa bridge UI."""
    if configured_spa_id and configured_spa_id in profiles:
        return configured_spa_id, profiles[configured_spa_id]
    if profiles:
        spa_id, profile = next(iter(profiles.items()))
        return spa_id, profile
    return configured_spa_id, {}


def _is_state_stale(timestamp: str | None, *, max_age_seconds: int = 120) -> bool:
    """Return whether a snapshot timestamp is missing, invalid, or too old."""
    if not timestamp:
        return True
    try:
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return (datetime.now(UTC) - parsed).total_seconds() > max_age_seconds
    except (AttributeError, TypeError, ValueError):
        logger.warning("Invalid state timestamp received: %s", timestamp)
        return True


class WebViewModels:
    """Build stable template contexts from Web UI collaborators."""

    def __init__(
        self,
        config: AppConfig,
        state_manager: StateManager,
        capability_detector: CapabilityDetector | None,
    ) -> None:
        self._config = config
        self._state_manager = state_manager
        self._capability_detector = capability_detector

    async def overview_context(self) -> dict[str, Any]:
        """Build the full context expected by ``overview.html``."""
        current_state = self._state_manager.get_latest_snapshot()
        state_available = current_state is not None
        if current_state is None:
            current_state = self._state_manager.get_safe_fallback_state()
        _ensure_display_shape(current_state)

        spa_id, capability = self._selected_capability()
        discovered_items = await _load_discovered_items()
        _sort_lights_for_display(current_state)
        last_updated = current_state.get("timestamp", datetime.now(UTC).isoformat())
        return {
            "state": current_state,
            "capability": capability or _EMPTY_CAPABILITY,
            "capability_available": bool(capability),
            "discovered_items": discovered_items.get(spa_id, {})
            if spa_id is not None
            else {},
            "mqtt_topic_prefix": (
                f"{self._config.mqtt.base_topic}/{spa_id}"
                if spa_id
                else self._config.mqtt.base_topic
            ),
            "config": self._config,
            "versions": get_version_info(),
            "state_available": state_available,
            "state_is_stale": current_state.get("quality", {}).get("status")
            in {"stale", "unavailable"}
            or _is_state_stale(last_updated),
            "last_updated": last_updated,
        }

    async def controls_context(self) -> dict[str, Any]:
        """Build the full context expected by ``controls.html``."""
        current_state = self._state_manager.get_latest_snapshot()
        state_available = current_state is not None
        if current_state is None:
            current_state = self._state_manager.get_safe_fallback_state()
        _ensure_display_shape(current_state)

        spa_id, capability = self._selected_capability()
        discovered_items = await _load_discovered_items()
        _sort_lights_for_display(current_state)
        if spa_id is not None:
            _add_detected_light_modes(current_state, discovered_items.get(spa_id, {}))
        last_updated = current_state.get("timestamp", datetime.now(UTC).isoformat())
        return {
            "capability": capability or _EMPTY_CAPABILITY,
            "capability_available": bool(capability),
            "spa_label": capability.get("model")
            or spa_id
            or "konfigurierter Whirlpool",
            "state": current_state,
            "config": self._config,
            "state_available": state_available,
            "state_is_stale": current_state.get("quality", {}).get("status")
            in {"stale", "unavailable"}
            or _is_state_stale(last_updated),
            "last_updated": last_updated,
        }

    def _selected_capability(self) -> tuple[str | None, dict[str, Any]]:
        profiles = (
            self._capability_detector.get_cached_profiles()
            if self._capability_detector is not None
            else {}
        )
        return _selected_capability(profiles, self._config.smarttub.device_id)
