"""HTTP endpoints that issue SmartTub control commands."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.command_models import (
    CloudCommandError,
    CommandError,
    CommandQueueFullError,
    CommandResult,
    CommandStatus,
    CommandValidationError,
    CommandVerificationError,
    ComponentNotFoundError,
    UnsupportedCommandError,
)
from src.core.command_validation import CommandValidator
from src.core.discovery_result_store import DiscoveryResultStore
from src.core.light_mode_catalog import available_light_mode_names
from src.core.smarttub_client import SmartTubClient
from src.web.errors import internal_server_error

logger = logging.getLogger(__name__)

CommandValue = float | int | str


def _identity(value: CommandValue) -> CommandValue:
    return value


def _switch_to_enabled(value: CommandValue) -> bool:
    return str(value).lower() == "on"


@dataclass(frozen=True)
class CommandSpec:
    """Static mapping between an HTTP command and its execution details."""

    command_path: str
    payload_key: str
    client_method: str
    client_value: Callable[[CommandValue], Any] = _identity
    component_id_key: str | None = None


COMMAND_SPECS = {
    "temperature": CommandSpec(
        "heater/target_temperature_writetopic", "temperature", "set_temperature"
    ),
    "heat_mode": CommandSpec("heater/mode_writetopic", "mode", "set_heat_mode"),
    "filtration_mode": CommandSpec(
        "filtration/mode_writetopic", "mode", "set_primary_filtration_mode"
    ),
    "pump_state": CommandSpec(
        "pumps/state_writetopic",
        "state",
        "set_pump_state",
        _switch_to_enabled,
        "pump_id",
    ),
    "light_state": CommandSpec(
        "lights/state_writetopic",
        "state",
        "set_light_state",
        _switch_to_enabled,
        "light_id",
    ),
    "light_color": CommandSpec(
        "lights/color_writetopic", "color", "set_light_color", _identity, "light_id"
    ),
    "light_brightness": CommandSpec(
        "lights/brightness_writetopic",
        "brightness",
        "set_light_brightness",
        _identity,
        "light_id",
    ),
    "light_mode": CommandSpec(
        "lights/mode_writetopic", "mode", "set_light_mode", _identity, "light_id"
    ),
}


async def _execute_command(
    spec: CommandSpec,
    value: CommandValue,
    smarttub_client: SmartTubClient | None,
    command_manager: Any,
    component_id: str | None = None,
    validator: CommandValidator | None = None,
) -> CommandResult:
    """Execute one command through the queue or direct client fallback."""
    payload = {spec.payload_key: value}
    if spec.component_id_key is not None and component_id is not None:
        payload[spec.component_id_key] = component_id
    payload = (validator or CommandValidator()).normalize(spec.command_path, payload)

    if command_manager is not None:
        result = await command_manager.execute_command(spec.command_path, payload)
        if isinstance(result, CommandResult):
            return result
        # Compatibility for injected command managers that predate structured
        # outcomes. A normal return proves only that dispatch did not fail.
        return CommandResult(
            uuid.uuid4().hex,
            spec.command_path,
            CommandStatus.SENT,
            "Command dispatched without an error",
        )
    if smarttub_client is None:
        raise HTTPException(status_code=503, detail="SmartTub client not available")
    method = getattr(smarttub_client, spec.client_method)
    if spec.component_id_key is None:
        operation_status = await method(spec.client_value(value))
    else:
        operation_status = await method(
            spec.client_value(value), **{spec.component_id_key: component_id}
        )
    status = (
        operation_status
        if isinstance(operation_status, CommandStatus)
        else CommandStatus.SENT
    )
    return CommandResult(
        uuid.uuid4().hex,
        spec.command_path,
        status,
        "SmartTub API read-back confirmed the requested state"
        if status is CommandStatus.CONFIRMED
        else "SmartTub API accepted the command without an error",
    )


def _success(message: str, result: CommandResult) -> dict[str, Any]:
    response: dict[str, Any] = {
        "status": result.status.value,
        "message": message,
        "timestamp": datetime.now(UTC).isoformat(),
        "command": result.to_dict(),
    }
    return response


def _command_http_error(exc: CommandError) -> HTTPException:
    headers = {"X-Command-Error-Code": exc.code}
    if isinstance(exc, CommandQueueFullError):
        return HTTPException(
            status_code=503,
            detail="Command queue is full; retry later",
            headers={**headers, "Retry-After": "1"},
        )
    if isinstance(exc, ComponentNotFoundError):
        return HTTPException(status_code=404, detail=str(exc), headers=headers)
    if isinstance(exc, CommandValidationError):
        return HTTPException(status_code=422, detail=str(exc), headers=headers)
    if isinstance(exc, CommandVerificationError):
        return HTTPException(status_code=409, detail=str(exc), headers=headers)
    if isinstance(exc, CloudCommandError):
        return HTTPException(
            status_code=503, detail="SmartTub command failed", headers=headers
        )
    return HTTPException(status_code=503, detail="Command failed", headers=headers)


class TemperatureCommand(BaseModel):
    temperature: float


class ModeCommand(BaseModel):
    mode: str = Field(min_length=1)


class SwitchCommand(BaseModel):
    state: str = Field(min_length=1)


class PumpStateCommand(SwitchCommand):
    pump_id: str = Field(min_length=1)


class LightStateCommand(SwitchCommand):
    light_id: str = Field(min_length=1)


class ColorCommand(BaseModel):
    color: str = Field(min_length=1)
    light_id: str = Field(min_length=1)


class BrightnessCommand(BaseModel):
    brightness: int = Field(ge=0, le=100)
    light_id: str = Field(min_length=1)


class LightModeCommand(BaseModel):
    mode: str = Field(min_length=1)
    light_id: str = Field(min_length=1)


def create_command_router(
    smarttub_client: SmartTubClient | None,
    command_manager: Any = None,
    discovery_result_store: DiscoveryResultStore | None = None,
    spa_id: str | None = None,
    capability_detector: Any = None,
) -> APIRouter:
    """Create the command API without coupling it to the web-app bootstrap."""
    router = APIRouter(tags=["commands"])

    def temperature_range() -> dict[str, float] | None:
        if capability_detector is None or spa_id is None:
            return None
        capabilities = capability_detector.get_cached_capabilities(spa_id)
        return (
            capabilities.heater_temperature_range if capabilities is not None else None
        )

    validator = CommandValidator(temperature_range)

    async def validate_light_mode(light_id: str, mode: str) -> str:
        """Validate a mode against the library catalogue and discovery results."""
        normalized_mode = mode.strip().upper()
        if normalized_mode not in set(available_light_mode_names()):
            raise UnsupportedCommandError(f"Unsupported light mode: {normalized_mode}")

        if discovery_result_store is None or spa_id is None:
            return normalized_mode

        detected_modes = await discovery_result_store.get_detected_modes_async(
            spa_id, light_id
        )
        if normalized_mode != "OFF" and not detected_modes:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Für {light_id} wurden noch keine Lichtmodi erkannt. "
                    "Bitte zuerst eine Erkennung ausführen."
                ),
            )
        if normalized_mode != "OFF" and normalized_mode not in detected_modes:
            raise HTTPException(
                status_code=422,
                detail=f"Lichtmodus {normalized_mode} wurde für {light_id} nicht erkannt",
            )
        return normalized_mode

    @router.post("/api/commands/set_temperature")
    async def set_temperature(command: TemperatureCommand) -> dict[str, Any]:
        """Set spa target temperature."""
        try:
            temperature = float(command.temperature)
            result = await _execute_command(
                COMMAND_SPECS["temperature"],
                temperature,
                smarttub_client,
                command_manager,
                validator=validator,
            )
            message = (
                f"Temperature confirmed at {temperature}°C"
                if result.status is CommandStatus.CONFIRMED
                else f"Temperature command sent for {temperature}°C"
            )
            return _success(message, result)
        except HTTPException:
            raise
        except CommandError as exc:
            raise _command_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Invalid temperature value"
            ) from exc
        except Exception as exc:
            raise internal_server_error(logger, "Failed to set temperature") from exc

    @router.post("/api/commands/set_heat_mode")
    async def set_heat_mode(command: ModeCommand) -> dict[str, Any]:
        """Set spa heating mode."""
        try:
            mode = str(command.mode)
            result = await _execute_command(
                COMMAND_SPECS["heat_mode"],
                mode,
                smarttub_client,
                command_manager,
                validator=validator,
            )
            return _success(f"Heat mode set to {mode}", result)
        except HTTPException:
            raise
        except CommandError as exc:
            raise _command_http_error(exc) from exc
        except Exception as exc:
            raise internal_server_error(logger, "Failed to set heat mode") from exc

    @router.post("/api/commands/set_filtration_mode")
    async def set_filtration_mode(command: ModeCommand) -> dict[str, Any]:
        """Set the primary filtration mode."""
        try:
            mode = str(command.mode)
            result = await _execute_command(
                COMMAND_SPECS["filtration_mode"],
                mode,
                smarttub_client,
                command_manager,
                validator=validator,
            )
            return _success(f"Filtration mode set to {mode}", result)
        except HTTPException:
            raise
        except CommandError as exc:
            raise _command_http_error(exc) from exc
        except Exception as exc:
            raise internal_server_error(
                logger, "Failed to set filtration mode"
            ) from exc

    @router.post("/api/commands/set_pump_state")
    async def set_pump_state(command: PumpStateCommand) -> dict[str, Any]:
        """Set the state of one identified pump."""
        try:
            state = command.state.strip().lower()
            result = await _execute_command(
                COMMAND_SPECS["pump_state"],
                state,
                smarttub_client,
                command_manager,
                command.pump_id,
                validator,
            )
            return _success(
                f"Pumpe {command.pump_id} {'eingeschaltet' if state == 'on' else 'ausgeschaltet'}",
                result,
            )
        except HTTPException:
            raise
        except CommandError as exc:
            raise _command_http_error(exc) from exc
        except Exception as exc:
            raise internal_server_error(logger, "Failed to set pump state") from exc

    @router.post("/api/commands/set_light_state")
    async def set_light_state(command: LightStateCommand) -> dict[str, Any]:
        """Set the state of one identified light zone."""
        try:
            state = command.state.strip().lower()
            result = await _execute_command(
                COMMAND_SPECS["light_state"],
                state,
                smarttub_client,
                command_manager,
                command.light_id,
                validator,
            )
            return _success(
                f"Licht {command.light_id} {'eingeschaltet' if state == 'on' else 'ausgeschaltet'}",
                result,
            )
        except HTTPException:
            raise
        except CommandError as exc:
            raise _command_http_error(exc) from exc
        except Exception as exc:
            raise internal_server_error(logger, "Failed to set light state") from exc

    @router.post("/api/commands/set_light_color")
    async def set_light_color(command: ColorCommand) -> dict[str, Any]:
        """Set light color."""
        try:
            color = str(command.color)
            result = await _execute_command(
                COMMAND_SPECS["light_color"],
                color,
                smarttub_client,
                command_manager,
                command.light_id,
                validator,
            )
            return _success(f"Farbe für {command.light_id} gesetzt", result)
        except HTTPException:
            raise
        except CommandError as exc:
            raise _command_http_error(exc) from exc
        except Exception as exc:
            raise internal_server_error(logger, "Failed to set light color") from exc

    @router.post("/api/commands/set_light_brightness")
    async def set_light_brightness(command: BrightnessCommand) -> dict[str, Any]:
        """Set light brightness."""
        try:
            brightness = int(command.brightness)
            result = await _execute_command(
                COMMAND_SPECS["light_brightness"],
                brightness,
                smarttub_client,
                command_manager,
                command.light_id,
                validator,
            )
            return _success(
                f"Helligkeit für {command.light_id} auf {brightness}% gesetzt",
                result,
            )
        except HTTPException:
            raise
        except CommandError as exc:
            raise _command_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Invalid brightness value"
            ) from exc
        except Exception as exc:
            raise internal_server_error(
                logger, "Failed to set light brightness"
            ) from exc

    @router.post("/api/commands/set_light_mode")
    async def set_light_mode(command: LightModeCommand) -> dict[str, Any]:
        """Set a discovered mode for one identified light zone."""
        try:
            mode = await validate_light_mode(command.light_id, command.mode)
            result = await _execute_command(
                COMMAND_SPECS["light_mode"],
                mode,
                smarttub_client,
                command_manager,
                command.light_id,
                validator,
            )
            return _success(f"Lichtmodus {mode} für {command.light_id} gesetzt", result)
        except HTTPException:
            raise
        except CommandError as exc:
            raise _command_http_error(exc) from exc
        except Exception as exc:
            raise internal_server_error(logger, "Failed to set light mode") from exc

    @router.get("/api/commands/history")
    async def get_command_history() -> dict[str, Any]:
        """Get recent command history."""
        if command_manager and hasattr(command_manager, "get_command_history"):
            commands = command_manager.get_command_history()
            return {"commands": commands, "total": len(commands)}
        return {
            "commands": [
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "command": "system_startup",
                    "status": "success",
                    "message": "System initialized",
                }
            ],
            "total": 1,
        }

    return router
