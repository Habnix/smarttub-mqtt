"""Shared command outcomes and domain errors.

The bridge can observe validation, queueing, SmartTub API responses and later
API reads. It cannot guarantee that a physical actuator reacted, so command
states deliberately describe only those observable boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class CommandStatus(StrEnum):
    """Observable lifecycle states for a command."""

    ACCEPTED = "accepted"
    SENT = "sent"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CommandResult:
    """Latest observable result returned to HTTP and internal callers."""

    command_id: str
    command: str
    status: CommandStatus
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "command_id": self.command_id,
            "command": self.command,
            "status": self.status.value,
            "message": self.message,
        }


class CommandError(Exception):
    """Base class for expected command failures."""

    code = "command_error"


class CommandValidationError(CommandError, ValueError):
    """A command payload or component identifier is invalid."""

    code = "validation_error"


class UnsupportedCommandError(CommandValidationError):
    """The requested operation/value is not supported by the current spa."""

    code = "unsupported_command"


class ComponentNotFoundError(CommandError, LookupError):
    """The requested pump or light does not exist in the current API state."""

    code = "component_not_found"


class CloudCommandError(CommandError):
    """The SmartTub API reported or raised an error while sending a command."""

    code = "cloud_command_failed"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class CommandVerificationError(CommandError):
    """A later API read contradicts an expected command result."""

    code = "verification_failed"


class CommandQueueFullError(CommandError):
    """The bounded command executor cannot accept more work."""

    code = "queue_full"


class CommandTimeoutError(CommandError):
    """A command exceeded its configured execution deadline."""

    code = "command_timeout"


__all__ = [
    "CloudCommandError",
    "CommandError",
    "CommandQueueFullError",
    "CommandResult",
    "CommandStatus",
    "CommandTimeoutError",
    "CommandValidationError",
    "CommandVerificationError",
    "ComponentNotFoundError",
    "UnsupportedCommandError",
]
