"""Shared light-mode catalogue for discovery and the WebUI.

The upstream library owns the complete vocabulary of light modes.  Keeping
the catalogue lookup here prevents the backend, the legacy prober, and the
browser from drifting apart when python-smarttub adds or removes a mode.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

QUICK_LIGHT_MODES: tuple[str, ...] = ("OFF", "ON", "PURPLE", "WHITE")
RGB_BRIGHTNESS_MODE = "FULL_DYNAMIC_RGB"
MODE_ONLY_LIGHT_MODES = frozenset(
    {
        "HIGH_SPEED_COLOR_WHEEL",
        "HIGH_SPEED_WHEEL",
        "LOW_SPEED_WHEEL",
        "FULL_DYNAMIC_RGB",
        "PARTY",
        "COLOR_WHEEL",
    }
)


class LightModeTestStatus(str, Enum):
    """Outcome categories for an active light-mode probe."""

    SUPPORTED = "supported"
    MODE_ONLY = "mode_only"
    BRIGHTNESS_UNSUPPORTED = "brightness_unsupported"
    API_REJECTED = "api_rejected"
    TIMEOUT = "timeout"
    ERROR = "error"
    CANCELLED = "cancelled"


def available_light_mode_names() -> tuple[str, ...]:
    """Return the light modes exposed by the installed upstream library."""
    from smarttub import SpaLight  # type: ignore[import-untyped]

    return tuple(mode.name for mode in SpaLight.LightMode)


def light_modes_for_discovery(mode: str) -> tuple[str, ...]:
    """Return the modes for a discovery run.

    The quick probe intentionally remains a stable, representative subset,
    while the full probe follows the installed library exactly.  Filtering
    the quick subset also keeps it safe if an upstream enum changes.
    """
    available = available_light_mode_names()
    if mode == "full":
        return available
    if mode == "quick":
        return tuple(name for name in QUICK_LIGHT_MODES if name in available)
    return ()


def light_mode_catalog() -> dict[str, Any]:
    """Return the catalogue consumed by the discovery API and browser."""
    all_modes = available_light_mode_names()
    quick_modes = tuple(name for name in QUICK_LIGHT_MODES if name in all_modes)
    return {
        "all": list(all_modes),
        "quick": list(quick_modes),
        "counts": {"all": len(all_modes), "quick": len(quick_modes)},
    }


def is_mode_detected(status: str | LightModeTestStatus) -> bool:
    """Whether an outcome proves that the requested mode can be selected."""
    value = status.value if isinstance(status, LightModeTestStatus) else status
    return value in {
        LightModeTestStatus.SUPPORTED.value,
        LightModeTestStatus.MODE_ONLY.value,
        LightModeTestStatus.BRIGHTNESS_UNSUPPORTED.value,
    }


def mode_uses_rgb_brightness(mode: str) -> bool:
    """Whether a mode's brightness is controlled through RGB values."""
    return mode.strip().upper() == RGB_BRIGHTNESS_MODE


def mode_is_mode_only(mode: str) -> bool:
    """Whether intensity is not a meaningful part of mode verification."""
    return mode.strip().upper() in MODE_ONLY_LIGHT_MODES
