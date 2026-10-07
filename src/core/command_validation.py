"""Transport-neutral validation and normalization for writable commands."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

from src.core.command_models import (
    CommandValidationError,
    UnsupportedCommandError,
)
from src.core.light_mode_catalog import available_light_mode_names

TemperatureRangeProvider = Callable[[], Mapping[str, float] | None]


class CommandValidator:
    """Turn HTTP or MQTT payloads into the same canonical command mapping."""

    def __init__(
        self, temperature_range_provider: TemperatureRangeProvider | None = None
    ) -> None:
        self._temperature_range_provider = temperature_range_provider

    def normalize(self, command_path: str, data: Any) -> dict[str, Any]:
        normalizers: dict[str, Callable[[Any], dict[str, Any]]] = {
            "heater/target_temperature_writetopic": self._temperature,
            "heater/mode_writetopic": lambda value: self._mode(value, "heat"),
            "filtration/mode_writetopic": lambda value: self._mode(value, "filtration"),
            "pumps/state_writetopic": lambda value: self._switch(
                value, "pump_id", "pump"
            ),
            "lights/state_writetopic": lambda value: self._switch(
                value, "light_id", "light"
            ),
            "lights/mode_writetopic": self._light_mode,
            "lights/color_writetopic": self._light_color,
            "lights/brightness_writetopic": self._brightness,
        }
        normalizer = normalizers.get(command_path)
        if normalizer is None:
            raise UnsupportedCommandError(f"Unsupported command path: {command_path}")
        return normalizer(data)

    @staticmethod
    def _value(data: Any, primary: str) -> Any:
        if not isinstance(data, Mapping):
            return data
        return data[primary] if primary in data else data.get("value")

    @staticmethod
    def _component_id(data: Any, key: str) -> str:
        value = data.get(key) if isinstance(data, Mapping) else None
        if not isinstance(value, str) or not value.strip():
            raise CommandValidationError(f"{key} is required")
        return value.strip()

    def _temperature(self, data: Any) -> dict[str, Any]:
        raw_value = self._value(data, "temperature")
        if raw_value is None or isinstance(raw_value, bool):
            raise CommandValidationError("temperature must be numeric")
        try:
            temperature = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise CommandValidationError("temperature must be numeric") from exc
        if not math.isfinite(temperature):
            raise CommandValidationError("temperature must be finite")

        bounds = (
            self._temperature_range_provider()
            if self._temperature_range_provider is not None
            else None
        )
        if bounds is not None:
            minimum = bounds.get("min")
            maximum = bounds.get("max")
            if minimum is not None and temperature < minimum:
                raise CommandValidationError(
                    f"temperature must be at least {float(minimum):g}°C"
                )
            if maximum is not None and temperature > maximum:
                raise CommandValidationError(
                    f"temperature must be at most {float(maximum):g}°C"
                )
        return {"temperature": temperature}

    def _mode(self, data: Any, label: str) -> dict[str, Any]:
        raw_value = self._value(data, "mode")
        mode = str(raw_value).strip().upper() if raw_value is not None else ""
        if not mode:
            raise CommandValidationError(f"{label} mode is required")
        return {"mode": mode}

    def _switch(self, data: Any, id_key: str, label: str) -> dict[str, Any]:
        raw_value = self._value(data, "state")
        state = str(raw_value).strip().lower() if raw_value is not None else ""
        if state not in {"on", "off"}:
            raise CommandValidationError(f"{label} state must be 'on' or 'off'")
        return {"state": state, id_key: self._component_id(data, id_key)}

    def _light_mode(self, data: Any) -> dict[str, Any]:
        normalized = self._mode(data, "light")
        mode = normalized["mode"]
        if mode not in set(available_light_mode_names()):
            raise UnsupportedCommandError(f"Unsupported light mode: {mode}")
        normalized["light_id"] = self._component_id(data, "light_id")
        return normalized

    def _light_color(self, data: Any) -> dict[str, Any]:
        raw_value = self._value(data, "color")
        color = str(raw_value).strip() if raw_value is not None else ""
        if not color:
            raise CommandValidationError("light color is required")
        return {
            "color": color,
            "light_id": self._component_id(data, "light_id"),
        }

    def _brightness(self, data: Any) -> dict[str, Any]:
        raw_value = self._value(data, "brightness")
        if isinstance(raw_value, bool):
            raise CommandValidationError("brightness must be an integer from 0 to 100")
        try:
            brightness = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise CommandValidationError(
                "brightness must be an integer from 0 to 100"
            ) from exc
        if isinstance(raw_value, float) and not raw_value.is_integer():
            raise CommandValidationError("brightness must be an integer from 0 to 100")
        if isinstance(raw_value, str) and str(brightness) != raw_value.strip():
            raise CommandValidationError("brightness must be an integer from 0 to 100")
        if not 0 <= brightness <= 100:
            raise CommandValidationError("brightness must be between 0 and 100")
        return {
            "brightness": brightness,
            "light_id": self._component_id(data, "light_id"),
        }
