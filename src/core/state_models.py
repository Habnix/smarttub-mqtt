"""Shared structural types for SmartTub state snapshots."""

from __future__ import annotations

from typing import Any, Literal, Required, TypedDict

StateQualityStatus = Literal["live", "stale", "unavailable"]


class StateQuality(TypedDict):
    """Describe whether component values are current observations."""

    status: StateQualityStatus
    observed_at: str | None
    last_success_at: str | None
    checked_at: str


class SpaComponent(TypedDict, total=False):
    state: str
    water_temperature: float | None
    air_temperature: float | None


class HeaterComponent(TypedDict, total=False):
    state: str
    temperature: float | None
    target_temperature: float | None


class PumpComponent(TypedDict, total=False):
    id: str
    type: str
    state: str
    speed: str
    speed_capability: str
    supported_speeds: list[str]
    raw_state: str
    raw_type: str
    raw_speed_capability: str


class LightComponent(TypedDict, total=False):
    id: str
    zone: int
    type: str
    state: str
    mode: str
    color: str
    brightness: int
    cycle_speed: Any
    detected_modes: list[str]


class StateComponents(TypedDict, total=False):
    spa: SpaComponent
    heater: HeaterComponent
    pumps: list[PumpComponent]
    lights: list[LightComponent]
    filtration: dict[str, Any]


class StateSnapshot(TypedDict, total=False):
    """Stable snapshot shape exchanged between core and MQTT layers."""

    timestamp: Required[str]
    spa_id: str
    # The state reader creates an observation first; StateManager adds quality
    # before publishing. Consumers must therefore still handle its absence at
    # that internal boundary.
    quality: StateQuality
    components: Required[StateComponents]
