from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from src.core.command_models import (
    CloudCommandError,
    CommandError,
    CommandQueueFullError,
    CommandResult,
    CommandStatus,
    CommandTimeoutError,
    CommandValidationError,
    ComponentNotFoundError,
)
from src.core.command_validation import CommandValidator
from src.core.config_loader import AppConfig
from src.core.log_safety import payload_summary
from src.core.smarttub_client import SmartTubClient
from src.mqtt.command_handlers import CommandHandlers
from src.mqtt.command_router import CommandRouter

if TYPE_CHECKING:
    from src.core.state_manager import StateManager

logger = logging.getLogger("smarttub.mqtt.commands")

type CommandHandler = Callable[[Any], Awaitable[CommandStatus]]
type QueuedCommand = (
    tuple[CommandHandler, Any]
    | tuple[CommandHandler, Any, asyncio.Future[CommandResult] | None]
    | tuple[
        CommandHandler,
        Any,
        asyncio.Future[CommandResult] | None,
        str,
        str,
    ]
)


class CommandManager:
    """Manages MQTT command subscriptions and execution."""

    def __init__(
        self,
        config: AppConfig,
        smarttub_client: SmartTubClient,
        mqtt_client: Any,
        capability_detector: Any = None,
    ):
        self.config = config
        self.smarttub_client = smarttub_client
        self.mqtt_client = mqtt_client
        self.capability_detector = capability_detector
        self._command_handlers: dict[str, CommandHandler] = {}
        queue_size = getattr(getattr(config, "safety", None), "command_queue_size", 100)
        self._command_queue: asyncio.Queue[QueuedCommand] = asyncio.Queue(
            maxsize=queue_size
        )
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._state_manager: StateManager | None = None
        self._router = CommandRouter(config.mqtt.base_topic)
        self._validator = CommandValidator(self._temperature_range)
        self._command_history: list[dict[str, Any]] = []
        self._worker_running = False
        self._transition_observers: list[Callable[[dict[str, Any]], None]] = []

        self._setup_command_handlers()

    def _setup_command_handlers(self) -> None:
        """Register the command actions without coupling them to MQTT plumbing."""
        self._command_actions = CommandHandlers(
            self.smarttub_client, self._trigger_state_update, self._validator
        )
        self._command_handlers = self._command_actions.as_mapping()

        # Keep the existing private aliases for callers and tests that inspect
        # the registered handler functions directly.
        self._handle_set_temperature = self._command_actions.set_temperature
        self._handle_set_heat_mode = self._command_actions.set_heat_mode
        self._handle_set_filtration_mode = self._command_actions.set_filtration_mode
        self._handle_set_pump_state = self._command_actions.set_pump_state
        self._handle_set_light_state = self._command_actions.set_light_state
        self._handle_set_light_mode = self._command_actions.set_light_mode
        self._handle_set_light_color = self._command_actions.set_light_color
        self._handle_set_light_brightness = self._command_actions.set_light_brightness

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the event loop for executing async handlers.

        This must be called before subscribing to commands to ensure
        handlers can be executed in the correct event loop.
        """
        self._event_loop = loop
        logger.debug(f"Event loop set for CommandManager: {loop}")

    def set_state_manager(self, state_manager: StateManager) -> None:
        """Set the state manager for triggering immediate state updates after commands.

        Args:
            state_manager: StateManager instance
        """
        self._state_manager = state_manager
        logger.debug("State manager set for CommandManager")

    async def process_command_queue(self) -> None:
        """Process commands from the queue in the main event loop.

        This should be run as a background task in the main event loop.
        """
        self._worker_running = True
        try:
            while True:
                queued = await self._command_queue.get()
                handler, data = queued[:2]
                completion = queued[2] if len(queued) >= 3 else None
                command_path = (
                    queued[3]
                    if len(queued) >= 4
                    else self._command_path_for_handler(handler)
                )
                command_id = queued[4] if len(queued) >= 5 else None
                if command_id is None:
                    command_id = self._accept_command(command_path)
                timeout = getattr(
                    getattr(self.config, "safety", None),
                    "command_timeout_seconds",
                    30,
                )
                operation = asyncio.ensure_future(handler(data))
                try:
                    handler_status = await asyncio.wait_for(operation, timeout)
                except TimeoutError as timeout_exc:
                    if operation.done() and not operation.cancelled():
                        operation_error = operation.exception()
                        exc = (
                            operation_error
                            if isinstance(operation_error, Exception)
                            else timeout_exc
                        )
                    else:
                        exc = CommandTimeoutError(
                            f"Command exceeded the {timeout}s execution timeout"
                        )
                    self._fail_command(command_id, command_path, completion, exc)
                except asyncio.CancelledError:
                    self._transition_command(
                        command_id,
                        command_path,
                        CommandStatus.UNKNOWN,
                        "Command processing stopped before completion",
                    )
                    if completion is not None and not completion.done():
                        completion.set_exception(
                            CommandError("Command processing stopped")
                        )
                    raise
                except Exception as exc:
                    logger.exception("Queued command failed")
                    self._fail_command(command_id, command_path, completion, exc)
                else:
                    status = (
                        handler_status
                        if isinstance(handler_status, CommandStatus)
                        else CommandStatus.SENT
                    )
                    result = self._transition_command(
                        command_id,
                        command_path,
                        status,
                        self._status_message(status),
                    )
                    if completion is not None and not completion.done():
                        completion.set_result(result)
                finally:
                    self._command_queue.task_done()
        finally:
            self._worker_running = False
            self._fail_queued_commands_on_shutdown()

    @property
    def is_worker_running(self) -> bool:
        """Whether the command queue consumer is currently active."""
        return self._worker_running

    def _fail_command(
        self,
        command_id: str,
        command_path: str,
        completion: asyncio.Future[CommandResult] | None,
        exc: Exception,
    ) -> None:
        self._transition_command(
            command_id,
            command_path,
            CommandStatus.FAILED,
            self._public_error_message(exc),
            error_code=exc.code if isinstance(exc, CommandError) else None,
        )
        if completion is not None and not completion.done():
            completion.set_exception(exc)

    def _fail_queued_commands_on_shutdown(self) -> None:
        while True:
            try:
                queued = self._command_queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            handler, _data = queued[:2]
            completion = queued[2] if len(queued) >= 3 else None
            command_path = (
                queued[3]
                if len(queued) >= 4
                else self._command_path_for_handler(handler)
            )
            command_id = queued[4] if len(queued) >= 5 else uuid.uuid4().hex
            self._transition_command(
                command_id,
                command_path,
                CommandStatus.UNKNOWN,
                "Command was not executed before shutdown",
            )
            if completion is not None and not completion.done():
                completion.set_exception(CommandError("Application is shutting down"))
            self._command_queue.task_done()

    async def subscribe_commands(self) -> None:
        """Subscribe to all command topics.

        Following T052 convention, we subscribe to _writetopic patterns for all
        writable values. Per-component write topics are also supported (e.g.,
        per-pump state_writetopic).
        """
        base_topic = self.config.mqtt.base_topic

        spa_id = self._configured_spa_id()
        # If cloud login is temporarily unavailable and no device ID has been
        # configured, subscribe safely with one spa-level wildcard. The router
        # still rejects every command until the client selects that exact spa.
        subscription_spa_id = spa_id or "+"

        # Subscribe only to the selected spa. This bridge is intentionally a
        # single-spa instance, so wildcard subscriptions could accept commands
        # intended for another device in the same SmartTub account.
        for command_path in self._command_handlers:
            topic = f"{base_topic}/{subscription_spa_id}/{command_path}"
            await self.mqtt_client.subscribe(topic, self._handle_command_message)
            logger.info(f"Subscribed to command topic: {topic}")

        # Also subscribe to per-pump command topics under:
        # <base_topic>/{spa_id}/pumps/{pump_id}/state_writetopic
        pump_topic = f"{base_topic}/{subscription_spa_id}/pumps/+/state_writetopic"
        await self.mqtt_client.subscribe(pump_topic, self._handle_command_message)
        logger.info(f"Subscribed to per-pump command topic: {pump_topic}")

        # Also subscribe to per-light command topics:
        # <base_topic>/{spa_id}/lights/{light_id}/state_writetopic
        # <base_topic>/{spa_id}/lights/{light_id}/mode_writetopic
        # <base_topic>/{spa_id}/lights/{light_id}/color_writetopic
        # <base_topic>/{spa_id}/lights/{light_id}/brightness_writetopic
        light_state_topic = (
            f"{base_topic}/{subscription_spa_id}/lights/+/state_writetopic"
        )
        await self.mqtt_client.subscribe(
            light_state_topic, self._handle_command_message
        )
        logger.info(f"Subscribed to per-light state command topic: {light_state_topic}")

        light_mode_topic = (
            f"{base_topic}/{subscription_spa_id}/lights/+/mode_writetopic"
        )
        await self.mqtt_client.subscribe(light_mode_topic, self._handle_command_message)
        logger.info(f"Subscribed to per-light mode command topic: {light_mode_topic}")

        light_color_topic = (
            f"{base_topic}/{subscription_spa_id}/lights/+/color_writetopic"
        )
        await self.mqtt_client.subscribe(
            light_color_topic, self._handle_command_message
        )
        logger.info(f"Subscribed to per-light color command topic: {light_color_topic}")

        light_brightness_topic = (
            f"{base_topic}/{subscription_spa_id}/lights/+/brightness_writetopic"
        )
        await self.mqtt_client.subscribe(
            light_brightness_topic, self._handle_command_message
        )
        logger.info(
            f"Subscribed to per-light brightness command topic: {light_brightness_topic}"
        )

    def _handle_command_message(self, topic: str, payload: Any) -> None:
        """Handle incoming command messages.

        Supports both the new _writetopic convention and per-component topics
        like pumps/{id}/state_writetopic or lights/{id}/brightness_writetopic.
        """
        logger.info(
            "mqtt-command-received",
            extra={
                "event": "mqtt-command-received",
                "topic": topic,
                **payload_summary(payload),
            },
        )
        try:
            if not self.smarttub_client.spas:
                logger.warning(
                    "mqtt-command-spa-unavailable",
                    extra={"event": "mqtt-command-spa-unavailable", "topic": topic},
                )
                return
        except AttributeError:
            logger.warning(f"Spa not available yet, ignoring command: {topic}")
            return
        try:
            route = self._router.resolve(topic, payload, self._command_handlers.keys())
            configured_spa_id = self._configured_spa_id()
            if route.spa_id != configured_spa_id:
                logger.warning(
                    "Ignoring MQTT command for unconfigured spa %s (configured: %s)",
                    route.spa_id,
                    configured_spa_id,
                )
                return
            handler = self._command_handlers.get(route.handler_key)
            if handler:
                normalized_data = self._validator.normalize(
                    route.handler_key, route.data
                )
                logger.info(
                    "mqtt-command-executing",
                    extra={
                        "event": "mqtt-command-executing",
                        "command": route.command_path,
                        "spa_id": route.spa_id,
                    },
                )
                self._execute_handler(handler, normalized_data, route.command_path)
            else:
                logger.warning(f"No handler found for command topic: {topic}")
        except CommandError as exc:
            command_path = route.command_path if "route" in locals() else topic
            self._transition_command(
                uuid.uuid4().hex,
                command_path,
                CommandStatus.FAILED,
                str(exc),
                error_code=exc.code,
            )
            logger.warning("Rejected invalid MQTT command %s: %s", topic, exc)
        except Exception:
            logger.exception("Error handling command %s", topic)

    def _configured_spa_id(self) -> str | None:
        """Return the one spa ID this bridge instance is allowed to control."""
        configured = getattr(getattr(self.config, "smarttub", None), "device_id", None)
        return str(configured) if configured is not None else None

    def _temperature_range(self) -> dict[str, float] | None:
        """Return observed bounds without inventing limits before detection."""
        spa_id = self._configured_spa_id()
        if self.capability_detector is None or spa_id is None:
            return None
        capabilities = self.capability_detector.get_cached_capabilities(spa_id)
        return (
            capabilities.heater_temperature_range if capabilities is not None else None
        )

    def _parse_payload(self, payload: Any) -> Any:
        """Parse payload as JSON if possible, otherwise return raw string."""
        return self._router.parse_payload(payload)

    def _normalize_command_data(
        self, raw_data: Any, pump_id: str | None = None, light_id: str | None = None
    ) -> dict[str, Any]:
        """Normalize command data into a consistent dict format.

        Args:
            raw_data: Parsed payload (dict, str, int, etc.)
            pump_id: Optional pump ID to inject
            light_id: Optional light ID to inject

        Returns:
            Normalized dict with injected IDs
        """
        return self._router.normalize_data(raw_data, pump_id=pump_id, light_id=light_id)

    async def _trigger_state_update(self) -> None:
        """Trigger an immediate state update after a successful command.

        This ensures MQTT state topics reflect the new hardware state
        without waiting for the next polling cycle.

        Adds a configurable delay to allow the SmartTub Cloud API to process
        the command before fetching the updated state. The delay compensates
        for cloud API propagation latency.

        The delay can be configured via:
        - YAML: smarttub.state_update_delay_seconds (default: 2.5)
        - ENV: STATE_UPDATE_DELAY_SECONDS (range: 0.5-10.0 seconds)
        """
        if self._state_manager is None:
            logger.warning(
                "State manager not set, cannot trigger immediate state update"
            )
            return

        try:
            delay = self.config.smarttub.state_update_delay_seconds
            logger.debug(f"Triggering immediate state update after {delay}s delay")
            # Wait for SmartTub Cloud API to process the command
            # The cloud API is slow and needs time to update its state
            await asyncio.sleep(delay)
            await self._state_manager.sync_state()
            logger.debug("Immediate state update completed")
        except Exception:
            logger.exception("Failed to trigger immediate state update")

    def _execute_handler(
        self, handler: CommandHandler, data: Any, command_path: str | None = None
    ) -> None:
        """Queue async handler for execution in the main event loop.

        This is called from the MQTT callback thread, so we can't directly
        use asyncio.create_task(). Instead, we queue the handler and data
        for processing by the main event loop.

        Args:
            handler: Async handler function to execute
            data: Data to pass to handler
        """
        resolved_path = command_path or self._command_path_for_handler(handler)
        command_id = uuid.uuid4().hex
        queued = (handler, data, None, resolved_path, command_id)
        try:
            self._command_queue.put_nowait(queued)
        except asyncio.QueueFull:
            self._transition_command(
                command_id,
                resolved_path,
                CommandStatus.FAILED,
                "Command queue is full",
            )
            logger.error("Rejected MQTT command because the command queue is full")
            return
        self._accept_command(resolved_path, command_id=command_id)
        logger.debug(f"Queued command handler: {handler.__name__}")

    async def execute_command(self, command_path: str, data: Any) -> CommandResult:
        """Run one Web command through the same serialized queue as MQTT.

        The caller awaits both the cloud command and its post-command state
        reconciliation, so the Web UI cannot overtake MQTT commands.
        """
        handler = self._command_handlers.get(command_path)
        if handler is None:
            raise ValueError(f"Unsupported command path: {command_path}")
        data = self._validator.normalize(command_path, data)

        completion: asyncio.Future[CommandResult] = (
            asyncio.get_running_loop().create_future()
        )
        command_id = uuid.uuid4().hex
        try:
            self._command_queue.put_nowait(
                (handler, data, completion, command_path, command_id)
            )
        except asyncio.QueueFull as exc:
            error = CommandQueueFullError("Command queue is full; retry later")
            self._transition_command(
                command_id,
                command_path,
                CommandStatus.FAILED,
                "Command queue is full",
            )
            raise error from exc
        self._accept_command(command_path, command_id=command_id)
        return await completion

    def get_command_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent completed commands without storing their payloads."""
        return deepcopy(list(reversed(self._command_history[-limit:])))

    def subscribe_transitions(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Subscribe to safe command-history snapshots after each transition."""
        if callback not in self._transition_observers:
            self._transition_observers.append(callback)

    def _command_path_for_handler(self, handler: CommandHandler) -> str:
        return next(
            (
                path
                for path, registered in self._command_handlers.items()
                if registered == handler
            ),
            getattr(handler, "__name__", "unknown"),
        )

    def _accept_command(
        self, command_path: str, *, command_id: str | None = None
    ) -> str:
        command_id = command_id or uuid.uuid4().hex
        self._transition_command(
            command_id,
            command_path,
            CommandStatus.ACCEPTED,
            "Command accepted and queued",
        )
        return command_id

    def _transition_command(
        self,
        command_id: str,
        command_path: str,
        status: CommandStatus,
        message: str,
        *,
        error_code: str | None = None,
    ) -> CommandResult:
        timestamp = datetime.now(UTC).isoformat()
        transition = {
            "timestamp": timestamp,
            "status": status.value,
            "message": message,
        }
        if error_code is not None:
            transition["error_code"] = error_code
        record = next(
            (
                item
                for item in self._command_history
                if item["command_id"] == command_id
            ),
            None,
        )
        if record is None:
            record = {
                "command_id": command_id,
                "command": command_path,
                "timestamp": timestamp,
                "status": status.value,
                "message": message,
                "transitions": [],
            }
            self._command_history.append(record)
            del self._command_history[:-50]
        record.update(
            {
                "timestamp": timestamp,
                "status": status.value,
                "message": message,
            }
        )
        if error_code is not None:
            record["error_code"] = error_code
        record["transitions"].append(transition)
        logger.info(
            "command-transition",
            extra={
                "event": "command-transition",
                "command_id": command_id,
                "command": command_path,
                "status": status.value,
                "error_code": error_code,
            },
        )
        self._publish_command_transition(
            command_id,
            command_path,
            status,
            message,
            timestamp,
            error_code,
        )
        for observer in tuple(getattr(self, "_transition_observers", ())):
            try:
                observer(deepcopy(record))
            except Exception:  # web observers must not block commands
                logger.exception("Command transition observer failed")
        return CommandResult(command_id, command_path, status, message)

    def _publish_command_transition(
        self,
        command_id: str,
        command_path: str,
        status: CommandStatus,
        message: str,
        timestamp: str,
        error_code: str | None = None,
    ) -> None:
        """Publish observable command progress for MQTT consumers."""
        if self.mqtt_client is None or not hasattr(self.mqtt_client, "publish_sync"):
            return
        spa_id = self._configured_spa_id()
        if spa_id is None:
            return
        topic = f"{self.config.mqtt.base_topic}/{spa_id}/commands/result"
        payload = {
            "command_id": command_id,
            "command": command_path,
            "status": status.value,
            "message": message,
            "timestamp": timestamp,
        }
        if error_code is not None:
            payload["error_code"] = error_code
        try:
            self.mqtt_client.publish_sync(
                topic,
                payload,
                qos=1,
                retain=False,
            )
        except Exception:
            # Result reporting must not turn a successfully sent hardware
            # command into a failure. The broker client records publish errors.
            logger.exception("Failed to publish MQTT command result")

    @staticmethod
    def _status_message(status: CommandStatus) -> str:
        return {
            CommandStatus.ACCEPTED: "Command accepted and queued",
            CommandStatus.SENT: "SmartTub API accepted the command without an error",
            CommandStatus.CONFIRMED: "Expected state was observed through the SmartTub API",
            CommandStatus.FAILED: "Command failed",
            CommandStatus.UNKNOWN: "Command was sent but its result could not be verified",
        }[status]

    @staticmethod
    def _public_error_message(exc: Exception) -> str:
        """Return a safe message for history, HTTP-adjacent data, and MQTT."""
        if isinstance(exc, ComponentNotFoundError):
            return str(exc)
        if isinstance(exc, CommandValidationError):
            return str(exc)
        if isinstance(exc, CloudCommandError):
            return "SmartTub command failed"
        if isinstance(exc, CommandTimeoutError):
            return "Command timed out"
        if isinstance(exc, CommandError):
            return "Command failed"
        return "Unexpected command failure"
