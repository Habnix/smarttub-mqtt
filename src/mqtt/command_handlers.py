"""Async SmartTub command handlers used by the MQTT command manager."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.core.command_models import CommandStatus
from src.core.command_validation import CommandValidator

logger = logging.getLogger("smarttub.mqtt.commands")


class CommandHandlers:
    """Execute domain commands independently from MQTT routing and queuing."""

    def __init__(
        self,
        smarttub_client: Any,
        trigger_state_update: Callable[[], Awaitable[None]],
        validator: CommandValidator | None = None,
    ):
        self.smarttub_client = smarttub_client
        self._trigger_state_update = trigger_state_update
        self.validator = validator or CommandValidator()

    def as_mapping(self) -> dict[str, Callable[[Any], Awaitable[CommandStatus]]]:
        """Return the stable MQTT command-path to handler mapping."""
        return {
            "heater/target_temperature_writetopic": self.set_temperature,
            "heater/mode_writetopic": self.set_heat_mode,
            "filtration/mode_writetopic": self.set_filtration_mode,
            "pumps/state_writetopic": self.set_pump_state,
            "lights/state_writetopic": self.set_light_state,
            "lights/mode_writetopic": self.set_light_mode,
            "lights/color_writetopic": self.set_light_color,
            "lights/brightness_writetopic": self.set_light_brightness,
        }

    async def _complete_command(
        self, operation: Awaitable[CommandStatus | None], message: str
    ) -> CommandStatus:
        """Run one cloud operation, record it, and reconcile the state once."""
        operation_status = await operation
        logger.info(message)
        await self._trigger_state_update()
        # A successful cloud call proves only that the command was sent. State
        # refresh alone is not command-specific verification and must not be
        # presented as physical confirmation.
        return (
            operation_status
            if isinstance(operation_status, CommandStatus)
            else CommandStatus.SENT
        )

    async def set_temperature(self, data: Any) -> CommandStatus:
        """Handle set temperature command."""
        temperature = self.validator.normalize(
            "heater/target_temperature_writetopic", data
        )["temperature"]
        return await self._complete_command(
            self.smarttub_client.set_temperature(temperature),
            f"Set temperature to {temperature}°C",
        )

    async def set_heat_mode(self, data: Any) -> CommandStatus:
        """Handle set heat mode command."""
        mode = self.validator.normalize("heater/mode_writetopic", data)["mode"]
        return await self._complete_command(
            self.smarttub_client.set_heat_mode(mode), f"Set heat mode to {mode}"
        )

    async def set_filtration_mode(self, data: Any) -> CommandStatus:
        """Handle a primary filtration mode command."""
        mode = self.validator.normalize("filtration/mode_writetopic", data)["mode"]
        return await self._complete_command(
            self.smarttub_client.set_primary_filtration_mode(mode),
            f"Set primary filtration mode to {mode}",
        )

    async def set_pump_state(self, data: Any) -> CommandStatus:
        """Handle set pump state command."""
        command = self.validator.normalize("pumps/state_writetopic", data)
        state, pump_id = command["state"], command["pump_id"]
        return await self._complete_command(
            self.smarttub_client.set_pump_state(state == "on", pump_id=pump_id),
            f"Pump control requested: {state} (pump_id={pump_id})",
        )

    async def set_light_state(self, data: Any) -> CommandStatus:
        """Handle set light state command."""
        command = self.validator.normalize("lights/state_writetopic", data)
        state, light_id = command["state"], command["light_id"]
        return await self._complete_command(
            self.smarttub_client.set_light_state(state == "on", light_id=light_id),
            f"Light control requested: {state} (light_id={light_id})",
        )

    async def set_light_mode(self, data: Any) -> CommandStatus:
        """Handle set light mode command (e.g., OFF, WHITE, PURPLE, LowSpeedWheel, ColorWheel)."""
        command = self.validator.normalize("lights/mode_writetopic", data)
        mode, light_id = command["mode"], command["light_id"]
        return await self._complete_command(
            self.smarttub_client.set_light_mode(mode, light_id=light_id),
            f"Light mode control requested: {mode} (light_id={light_id})",
        )

    async def set_light_color(self, data: Any) -> CommandStatus:
        """Handle set light color command."""
        command = self.validator.normalize("lights/color_writetopic", data)
        color, light_id = command["color"], command["light_id"]
        return await self._complete_command(
            self.smarttub_client.set_light_color(color, light_id=light_id),
            f"Light color control requested: {color} (light_id={light_id})",
        )

    async def set_light_brightness(self, data: Any) -> CommandStatus:
        """Handle set light brightness command."""
        command = self.validator.normalize("lights/brightness_writetopic", data)
        brightness, light_id = command["brightness"], command["light_id"]
        return await self._complete_command(
            self.smarttub_client.set_light_brightness(brightness, light_id=light_id),
            f"Light brightness control requested: {brightness}% (light_id={light_id})",
        )
