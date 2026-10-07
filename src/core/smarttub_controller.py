"""SmartTub control operations separated from connection and state reading."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from src.core.command_models import (
    CloudCommandError,
    CommandStatus,
    CommandValidationError,
    CommandVerificationError,
    ComponentNotFoundError,
    UnsupportedCommandError,
)
from src.core.light_mode_catalog import available_light_mode_names
from src.core.pump_model import normalize_pump_state
from src.core.smarttub_gateway import SmartTubGateway

logger = logging.getLogger("smarttub.api")
_UPSTREAM_STATE_CHANGE_TIMEOUT = "State change not reflected within timeout period"


class _ControllerClient(Protocol):
    """Structural client boundary that avoids a controller/client import cycle."""

    _spas: list[Any]
    gateway: SmartTubGateway


class SmartTubController:
    """Execute write operations against the client current spa."""

    def __init__(self, client: _ControllerClient) -> None:
        self.client = client
        self.gateway = client.gateway

    def _current_spa(self) -> Any:
        if not self.client._spas:
            raise ComponentNotFoundError("No spa available for control")
        return self.client._spas[0]

    @staticmethod
    def _required_zone(light_id: str | None) -> int:
        if not light_id:
            raise CommandValidationError("light_id is required")
        prefix, separator, raw_zone = light_id.partition("_")
        if prefix != "zone" or separator != "_" or not raw_zone.isdigit():
            raise CommandValidationError(
                f"Invalid light_id {light_id!r}; expected 'zone_<number>'"
            )
        return int(raw_zone)

    async def set_temperature(self, temperature_c: float) -> CommandStatus:
        """Set the spa target temperature.

        Args:
            temperature_c: Target temperature in Celsius
        """
        spa = self._current_spa()
        try:
            await spa.set_temperature(temperature_c)
        except Exception as exc:
            # python-smarttub sends the PATCH before it waits for an exact
            # read-back. Its timeout therefore means "sent but unverified",
            # not that the cloud rejected the command.
            if isinstance(exc, RuntimeError) and str(exc) == (
                _UPSTREAM_STATE_CHANGE_TIMEOUT
            ):
                logger.warning(
                    "Temperature command was sent but not reflected before "
                    "the upstream read-back timeout"
                )
                return CommandStatus.UNKNOWN
            raise CloudCommandError("Failed to set target temperature") from exc
        logger.info(f"Set spa temperature to {temperature_c}°C")
        # The pinned upstream method returns only after its command-specific
        # read-back observes the requested set point.
        return CommandStatus.CONFIRMED

    async def set_heat_mode(self, mode: str) -> None:
        """Set the spa heating mode.

        Args:
            mode: Heat mode (e.g., 'AUTO', 'ECONOMY', 'DAY', 'READY', 'REST')
        """
        spa = self._current_spa()

        # Map string mode to SmartTub enum
        # HeatMode is defined locally in Spa class
        heat_mode = getattr(spa, "HeatMode", None)
        normalized_mode = str(mode).strip().upper()
        if heat_mode:
            mode_enum = getattr(heat_mode, normalized_mode, None)
            if mode_enum is None:
                raise UnsupportedCommandError(
                    f"Unsupported heat mode {normalized_mode!r}"
                )
            try:
                await spa.set_heat_mode(mode_enum)
            except Exception as exc:
                raise CloudCommandError(
                    f"Failed to set heat mode {normalized_mode}"
                ) from exc
            logger.info(f"Set spa heat mode to {normalized_mode}")
        else:
            raise UnsupportedCommandError("Heat mode control is not available")

    async def set_primary_filtration_mode(self, mode: str) -> None:
        """Set the primary filtration mode, including ``ECO_MODE``."""
        spa = self._current_spa()
        try:
            status = await spa.get_status()
        except Exception as exc:
            raise CloudCommandError("Failed to read primary filtration") from exc
        filtration = getattr(status, "primary_filtration", None)
        if filtration is None:
            raise UnsupportedCommandError(
                "Primary filtration is not available on this spa"
            )

        normalized_mode = str(mode).strip().upper()
        enum_type = getattr(type(filtration), "PrimaryFiltrationMode", None)
        if enum_type is None:
            from smarttub import SpaPrimaryFiltrationCycle  # type: ignore

            enum_type = SpaPrimaryFiltrationCycle.PrimaryFiltrationMode

        mode_enum = getattr(enum_type, normalized_mode, None)
        if mode_enum is None:
            supported_modes = [getattr(item, "name", str(item)) for item in enum_type]
            raise UnsupportedCommandError(
                f"Unsupported primary filtration mode {mode!r}; "
                f"supported modes: {', '.join(supported_modes)}"
            )

        try:
            await filtration.set(mode=mode_enum)
        except Exception as exc:
            raise CloudCommandError(
                f"Failed to set primary filtration mode {normalized_mode}"
            ) from exc
        logger.info("Set primary filtration mode to %s", normalized_mode)

    async def set_pump_state(
        self, enabled: bool, pump_id: str | None = None
    ) -> CommandStatus:
        """Set a pump through the public toggle API and verify each transition.

        Args:
            enabled: True to turn pump on, False to turn off
            pump_id: Pump identifier (e.g. 'P1', 'P2', 'CP')
        """
        spa = self._current_spa()
        if not pump_id:
            raise CommandValidationError("pump_id is required")
        logger.info(
            "Attempting to set pump state",
            extra={"pump_id": pump_id, "enabled": enabled},
        )

        try:
            pumps = await spa.get_pumps()
        except Exception as exc:
            raise CloudCommandError("Failed to read pumps before command") from exc
        logger.debug(f"Retrieved {len(pumps)} pump objects from spa.get_pumps()")

        target_pump = next((pump for pump in pumps if pump.id == pump_id), None)
        if target_pump is None:
            raise ComponentNotFoundError(f"Pump {pump_id!r} was not found")

        current_state, current_speed = normalize_pump_state(target_pump.state)
        if current_state == "unknown":
            raise CommandVerificationError(
                f"Pump {target_pump.id} has an unknown state; refusing to toggle"
            )
        current_state_is_on = current_state == "on"
        if current_state_is_on == enabled:
            logger.info(
                "Pump %s already in desired state (%s)",
                target_pump.id,
                current_speed if current_state_is_on else current_state,
            )
            return CommandStatus.CONFIRMED

        # A two-speed pump can require LOW -> HIGH -> OFF. Re-read after each
        # public toggle and stop immediately when the requested binary state is
        # observed. ON from OFF always needs at most one transition.
        max_transitions = 1 if enabled or current_speed != "low" else 2
        current_pump = target_pump
        for transition in range(1, max_transitions + 1):
            toggle = getattr(current_pump, "toggle", None)
            if not callable(toggle):
                raise UnsupportedCommandError(
                    f"Pump {target_pump.id} does not expose toggle control"
                )
            try:
                await toggle()
            except Exception as exc:
                # SpaPump.toggle() sends the POST before waiting for its own
                # read-back. The pinned upstream timeout therefore cannot be
                # treated as proof that sending failed.
                if isinstance(exc, RuntimeError) and str(exc) == (
                    _UPSTREAM_STATE_CHANGE_TIMEOUT
                ):
                    logger.warning(
                        "Pump %s was toggled but the upstream read-back timed out",
                        target_pump.id,
                    )
                    return CommandStatus.UNKNOWN
                raise CloudCommandError(
                    f"Failed to send command for pump {target_pump.id}"
                ) from exc
            logger.info(
                "Sent toggle %d/%d for pump %s",
                transition,
                max_transitions,
                target_pump.id,
            )

            try:
                refreshed_pumps = await spa.get_pumps()
            except Exception:
                logger.exception(
                    "Pump %s was toggled but read-back failed", target_pump.id
                )
                return CommandStatus.UNKNOWN
            current_pump = next(
                (pump for pump in refreshed_pumps if pump.id == pump_id), None
            )
            if current_pump is None:
                return CommandStatus.UNKNOWN
            observed_state, current_speed = normalize_pump_state(current_pump.state)
            if observed_state == "unknown":
                return CommandStatus.UNKNOWN
            if (observed_state == "on") == enabled:
                logger.info(
                    "Confirmed pump %s state through SmartTub API: %s/%s",
                    target_pump.id,
                    observed_state,
                    current_speed,
                )
                return CommandStatus.CONFIRMED

        raise CommandVerificationError(
            f"Pump {target_pump.id} did not reach the requested state"
        )

    async def set_light_state(self, enabled: bool, light_id: str | None = None) -> None:
        """Set the spa light state (ON/OFF).

        Uses direct API calls to avoid python-smarttub library bug.

        Args:
            enabled: True to turn light on, False to turn off
            light_id: Light zone ID (e.g., "zone_1" for zone 1)
        """
        spa = self._current_spa()
        zone = self._required_zone(light_id)
        try:
            lights = await spa.get_lights()
        except Exception as exc:
            raise CloudCommandError("Failed to read lights before command") from exc
        if not lights:
            raise ComponentNotFoundError("No lights are available to control")

        # Find matching light
        target_light = next((light for light in lights if light.zone == zone), None)
        if target_light is None:
            raise ComponentNotFoundError(f"Light zone {zone} was not found")

        # Set light mode (ON/OFF)
        # Use direct API to avoid python-smarttub library bug
        try:
            if enabled:
                # Get current light state to check zone type
                lights_data = await self.gateway.get_raw_lights(spa)
                current_light = next(
                    (
                        light
                        for light in lights_data
                        if light.get("zone") == target_light.zone
                    ),
                    None,
                )

                logger.debug(
                    f"Light ON: target_light.zone={target_light.zone}, current_light={current_light}"
                )

                # Check if light supports RGB by looking at current mode
                # If mode is FULL_DYNAMIC_RGB or any RGB-capable mode, restore color
                current_mode = current_light.get("mode") if current_light else None
                is_rgb_capable = current_mode == "FULL_DYNAMIC_RGB"

                if current_light and is_rgb_capable:
                    # For RGB lights: restore last color or use default white
                    color_obj = current_light.get("color", {})
                    red = color_obj.get("red", 85)
                    green = color_obj.get("green", 85)
                    blue = color_obj.get("blue", 85)

                    logger.debug(
                        f"RGB light detected (mode={current_mode}), setting RGB=({red},{green},{blue})"
                    )

                    await self.gateway.patch_light(
                        spa,
                        target_light.zone,
                        {
                            "mode": "FULL_DYNAMIC_RGB",
                            "red": red,
                            "green": green,
                            "blue": blue,
                        },
                    )
                    logger.info(
                        f"Set RGB light zone {target_light.zone} to ON (RGB={red},{green},{blue})"
                    )
                else:
                    logger.debug(
                        f"Non-RGB light: current_light exists={current_light is not None}, mode={current_mode}"
                    )
                    # For non-RGB lights: use WHITE mode
                    await self.gateway.patch_light(
                        spa,
                        target_light.zone,
                        {"mode": "WHITE", "intensity": 50},
                    )
                    logger.info(
                        f"Set light zone {target_light.zone} to ON (WHITE, 50%)"
                    )
            else:
                # Turn off
                await self.gateway.patch_light(
                    spa,
                    target_light.zone,
                    {"mode": "OFF", "intensity": 0},
                )
                logger.info(f"Set light zone {target_light.zone} to OFF")
        except Exception as exc:
            raise CloudCommandError(
                f"Failed to set light state for zone {target_light.zone}"
            ) from exc

    async def set_light_mode(self, mode: str, light_id: str | None = None) -> None:
        """Set the spa light mode.

        Args:
            mode: Light mode (e.g., OFF, WHITE, PURPLE, RED, COLOR_WHEEL, etc.)
            light_id: Light zone ID
        """
        mode_upper = str(mode).strip().upper()
        if mode_upper not in set(available_light_mode_names()):
            raise ValueError(f"Unsupported light mode: {mode}")

        spa = self._current_spa()
        zone = self._required_zone(light_id)
        try:
            lights = await spa.get_lights()
        except Exception as exc:
            raise CloudCommandError("Failed to read lights before command") from exc
        if not lights:
            raise ComponentNotFoundError("No lights are available to control")

        target_light = next((light for light in lights if light.zone == zone), None)
        if target_light is None:
            raise ComponentNotFoundError(f"Light zone {zone} was not found")

        # Convert mode string and set via direct API to avoid python-smarttub library bug
        try:
            body: dict[str, object] = {"mode": mode_upper}
            if mode_upper == "OFF":
                body["intensity"] = 0
            # Wheel and dynamic modes ignore intensity and switch to their
            # hardware default. Do not send a misleading 50% value.

            await self.gateway.patch_light(spa, target_light.zone, body)
            logger.info(
                "Set light zone %s mode to %s",
                target_light.zone,
                mode_upper,
            )
        except Exception as exc:
            raise CloudCommandError(
                f"Failed to set light mode for zone {target_light.zone}"
            ) from exc

    async def set_light_color(self, color: str, light_id: str | None = None) -> None:
        """Set the spa light color.

        Supports multiple formats:
        - RGB decimal: "255,0,0" or "255 0 0"
        - RGB hex: "#ff0000" or "ff0000"
        - RGB JSON: '{"red":255,"green":0,"blue":0}' or '{"r":255,"g":0,"b":0}'
        - Color name: "RED", "BLUE", etc. (sets light mode, not RGB)

        Args:
            color: Color value in one of the supported formats
            light_id: Light zone ID (e.g., "zone_1")
        """
        spa = self._current_spa()
        zone = self._required_zone(light_id)

        # Try to parse as RGB value
        rgb = self._parse_rgb_color(color)

        if rgb is not None:
            # RGB value detected - use direct API call for FULL_DYNAMIC_RGB
            try:
                await self.gateway.patch_light(
                    spa,
                    zone,
                    {"color": {"red": rgb[0], "green": rgb[1], "blue": rgb[2]}},
                )
                logger.info(
                    f"Set light zone {zone} to RGB({rgb[0]}, {rgb[1]}, {rgb[2]})"
                )
            except Exception as exc:
                raise CloudCommandError(
                    f"Failed to set RGB color for zone {zone}"
                ) from exc
        else:
            # Color name - use legacy mode switching
            color_map = {
                "RED": "RED",
                "BLUE": "BLUE",
                "GREEN": "GREEN",
                "PURPLE": "PURPLE",
                "ORANGE": "ORANGE",
                "YELLOW": "YELLOW",
                "AQUA": "AQUA",
                "WHITE": "WHITE",
                "AMBER": "AMBER",
            }
            mode = color_map.get(color.upper(), color.upper())
            await self.set_light_mode(mode, light_id)

    def _parse_rgb_color(self, color: str) -> tuple[int, int, int] | None:
        """Parse RGB color from various formats.

        Supported formats:
        - Decimal: "255,0,0" or "255 0 0"
        - Hex: "#ff0000" or "ff0000"
        - JSON: '{"red":255,"green":0,"blue":0}' or '{"r":255,"g":0,"b":0}'

        Returns:
            Tuple of (r, g, b) values (0-255) or None if not RGB format
        """
        import json
        import re

        color = color.strip()

        # Try JSON format
        if color.startswith("{"):
            try:
                data = json.loads(color)
                if not isinstance(data, dict):
                    return None
                r = data["red"] if "red" in data else data.get("r")
                g = data["green"] if "green" in data else data.get("g")
                b = data["blue"] if "blue" in data else data.get("b")
                if r is not None and g is not None and b is not None:
                    return (
                        self._clamp_rgb(int(r)),
                        self._clamp_rgb(int(g)),
                        self._clamp_rgb(int(b)),
                    )
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        # Try hex format
        color = color.removeprefix("#")
        if re.match(r"^[0-9a-fA-F]{6}$", color):
            try:
                r = int(color[0:2], 16)
                g = int(color[2:4], 16)
                b = int(color[4:6], 16)
                return (r, g, b)
            except ValueError:
                pass

        # Try decimal format (comma or space separated)
        parts = re.split(r"[,\s]+", color)
        if len(parts) == 3:
            try:
                r, g, b = [int(p.strip()) for p in parts]
                return (self._clamp_rgb(r), self._clamp_rgb(g), self._clamp_rgb(b))
            except ValueError:
                pass

        return None

    def _clamp_rgb(self, value: int) -> int:
        """Clamp RGB value to 0-255 range."""
        return max(0, min(255, value))

    async def set_light_brightness(
        self, brightness: int, light_id: str | None = None
    ) -> None:
        """Set the spa light brightness using RGB scaling.

        For FULL_DYNAMIC_RGB mode:
        - Scales current RGB values proportionally
        - Uses white calibration if currently off (all RGB=0)

        For other modes:
        - Falls back to intensity field (known to be unreliable)

        Args:
            brightness: Brightness level (0-100)
            light_id: Light zone ID
        """
        if isinstance(brightness, bool) or not 0 <= brightness <= 100:
            raise CommandValidationError("brightness must be between 0 and 100")
        spa = self._current_spa()
        zone = self._required_zone(light_id)

        # Get current light state via direct API (library objects don't have color data)
        try:
            lights_data = await self.gateway.get_raw_lights(spa)
        except Exception as exc:
            raise CloudCommandError("Failed to read light brightness state") from exc
        if not lights_data:
            raise ComponentNotFoundError("No lights are available to control")

        target_light = next(
            (light for light in lights_data if light.get("zone") == zone), None
        )
        if target_light is None:
            raise ComponentNotFoundError(f"Light zone {zone} was not found")

        current_mode_name = target_light.get("mode", "UNKNOWN")

        # For FULL_DYNAMIC_RGB: Use RGB-based brightness control with hardware calibration
        if current_mode_name == "FULL_DYNAMIC_RGB":
            color_obj = target_light.get("color", {})
            current_r = color_obj.get("red", 0)
            current_g = color_obj.get("green", 0)
            current_b = color_obj.get("blue", 0)

            # Hardware limits RGB to ~85 at "100% brightness"
            hardware_max_rgb = 85
            current_max_rgb = max(current_r, current_g, current_b)

            # Calculate current brightness in hardware scale (0-100%)
            if current_max_rgb > 0:
                current_brightness = (current_max_rgb / hardware_max_rgb) * 100.0
            else:
                current_brightness = 0

            if current_brightness > 0:
                # Scale RGB proportionally based on hardware range
                target_max_rgb = int((brightness / 100.0) * hardware_max_rgb)
                scale_factor = target_max_rgb / current_max_rgb
                new_r = int(min(hardware_max_rgb, current_r * scale_factor))
                new_g = int(min(hardware_max_rgb, current_g * scale_factor))
                new_b = int(min(hardware_max_rgb, current_b * scale_factor))
            else:
                # Currently off - use white calibration or default white
                white_rgb = self._get_white_calibration(zone)
                target_max_rgb = int((brightness / 100.0) * hardware_max_rgb)
                # Scale white to hardware range
                max_white = max(white_rgb)
                if max_white > 0:
                    scale = target_max_rgb / max_white
                    new_r = int(min(hardware_max_rgb, white_rgb[0] * scale))
                    new_g = int(min(hardware_max_rgb, white_rgb[1] * scale))
                    new_b = int(min(hardware_max_rgb, white_rgb[2] * scale))
                else:
                    # Fallback to equal white
                    new_r = new_g = new_b = target_max_rgb

            try:
                await self.gateway.patch_light(
                    spa,
                    zone,
                    {"color": {"red": new_r, "green": new_g, "blue": new_b}},
                )
                logger.info(
                    f"Set light zone {zone} brightness to {brightness}% via RGB({new_r}, {new_g}, {new_b})"
                )
            except Exception as exc:
                raise CloudCommandError(
                    f"Failed to set RGB brightness for zone {zone}"
                ) from exc
        else:
            # For other modes: Use direct API call (intensity field is unreliable but no alternative)
            try:
                await self.gateway.patch_light(
                    spa,
                    zone,
                    {"mode": current_mode_name, "intensity": brightness},
                )
                logger.info(
                    f"Set light zone {zone} brightness to {brightness}% via intensity field (mode={current_mode_name}, unreliable)"
                )
            except Exception as exc:
                raise CloudCommandError(
                    f"Failed to set brightness for zone {zone}"
                ) from exc

    def _get_white_calibration(self, zone: int | None) -> tuple[int, int, int]:
        """Get white calibration RGB values for a zone.

        Returns calibrated white RGB or default (255, 255, 255).
        """
        # TODO: Load from discovered_items.yaml when white calibration is implemented
        return (255, 255, 255)
