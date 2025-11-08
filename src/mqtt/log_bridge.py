"""Structured logging configuration with optional MQTT forwarding."""

from __future__ import annotations

import json
import logging
from typing import Any

import structlog

from src.core.config_loader import AppConfig
from src.core.log_rotation import setup_file_logging


class _MQTTForwarder:
    def __init__(self, enabled: bool, mqtt_client: Any, topic: str) -> None:
        self._enabled = enabled
        self._mqtt_client = mqtt_client
        self._topic = topic

    def __call__(self, _: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        if self._enabled and self._mqtt_client is not None:
            try:
                payload = json.dumps(event_dict, default=str)
                self._mqtt_client.publish(self._topic, payload, 0, False)
            except Exception:  # pragma: no cover - forwarding should not break logging
                pass
        return event_dict


class CommandAuditLogger:
    """Logger for command audit events with MQTT forwarding."""

    def __init__(self, config: AppConfig, mqtt_client: Any):
        self.config = config
        self.mqtt_client = mqtt_client
        base_topic = (config.mqtt.base_topic or "smarttub-mqtt").rstrip("/")
        self.audit_topic = f"{base_topic}/meta/commands"
        self._enabled = config.logging.mqtt_forwarding

    def log_command_attempt(self, command_id: str, command_type: str,
                          command_params: dict[str, Any], user_id: str = "system") -> None:
        """Log a command attempt.

        Args:
            command_id: Unique identifier for the command
            command_type: Type of command (e.g., 'set_temperature')
            command_params: Parameters passed to the command
            user_id: Identifier for the user initiating the command
        """
        event = {
            "event": "command_attempt",
            "command_id": command_id,
            "command_type": command_type,
            "command_params": command_params,
            "user_id": user_id,
            "timestamp": structlog.processors.TimeStamper(fmt="iso", utc=True)(None, None, {})["timestamp"]
        }
        self._log_audit_event(event)

    def log_command_success(self, command_id: str, command_type: str,
                          result: dict[str, Any] = None) -> None:
        """Log a successful command execution.

        Args:
            command_id: Unique identifier for the command
            command_type: Type of command
            result: Result data from the command execution
        """
        event = {
            "event": "command_success",
            "command_id": command_id,
            "command_type": command_type,
            "result": result or {},
            "timestamp": structlog.processors.TimeStamper(fmt="iso", utc=True)(None, None, {})["timestamp"]
        }
        self._log_audit_event(event)

    def log_command_failure(self, command_id: str, command_type: str,
                          error: str, error_details: dict[str, Any] = None) -> None:
        """Log a failed command execution.

        Args:
            command_id: Unique identifier for the command
            command_type: Type of command
            error: Error message
            error_details: Additional error details
        """
        event = {
            "event": "command_failure",
            "command_id": command_id,
            "command_type": command_type,
            "error": error,
            "error_details": error_details or {},
            "timestamp": structlog.processors.TimeStamper(fmt="iso", utc=True)(None, None, {})["timestamp"]
        }
        self._log_audit_event(event)

    def log_command_timeout(self, command_id: str, command_type: str,
                          timeout_seconds: int) -> None:
        """Log a command timeout.

        Args:
            command_id: Unique identifier for the command
            command_type: Type of command
            timeout_seconds: Timeout duration in seconds
        """
        event = {
            "event": "command_timeout",
            "command_id": command_id,
            "command_type": command_type,
            "timeout_seconds": timeout_seconds,
            "timestamp": structlog.processors.TimeStamper(fmt="iso", utc=True)(None, None, {})["timestamp"]
        }
        self._log_audit_event(event)

    def _log_audit_event(self, event: dict[str, Any]) -> None:
        """Log an audit event to both structured logging and MQTT.

        Args:
            event: Audit event data
        """
        # Log to structured logging
        logger = structlog.get_logger("command_audit")
        logger.info("Command audit event", **event)

        # Forward to MQTT if enabled
        if self._enabled and self.mqtt_client is not None:
            try:
                payload = json.dumps(event, default=str)
                self.mqtt_client.publish(self.audit_topic, payload, qos=1, retain=False)
            except Exception as e:  # pragma: no cover - forwarding should not break operations
                logger.warning("Failed to forward command audit to MQTT", error=str(e))


def _resolve_log_level(level: str | None) -> int:
    candidate = (level or "info").upper()
    value = logging.getLevelName(candidate)
    return value if isinstance(value, int) else logging.INFO


def configure_log_bridge(config: AppConfig, mqtt_client: Any) -> None:
    base_topic = (config.mqtt.base_topic or "smarttub-mqtt").rstrip("/")
    forwarder = _MQTTForwarder(config.logging.mqtt_forwarding, mqtt_client, f"{base_topic}/meta/logs")

    min_level = _resolve_log_level(config.logging.level)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    # Set up file logging with rotation and ZIP compression
    file_handlers = setup_file_logging(
        log_dir=config.logging.log_dir,
        log_max_size_mb=config.logging.log_max_size_mb,
        log_max_files=config.logging.log_max_files,
        log_compress=config.logging.log_compress,
        log_level=min_level,
    )

    # Configure structlog to use standard logging
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(min_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.processors.add_log_level,
            timestamper,
            forwarder,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
    )

    # Configure standard logging to also write to files
    root_logger = logging.getLogger()
    root_logger.setLevel(min_level)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add console handler to root (all logs to console)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(min_level)
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Add default smarttub.log to root for catchall
    root_logger.addHandler(file_handlers["smarttub"])
    
    # Set up logger routing for specific modules with propagate=False to avoid duplicates
    # MQTT logs go ONLY to mqtt.log
    mqtt_logger = logging.getLogger("smarttub.mqtt")
    mqtt_logger.setLevel(min_level)
    mqtt_logger.propagate = False  # Don't propagate to root/parent
    mqtt_logger.addHandler(file_handlers["mqtt"])
    mqtt_logger.addHandler(console_handler)
    
    # WebUI logs go ONLY to webui.log  
    webui_logger = logging.getLogger("smarttub.webui")
    webui_logger.setLevel(min_level)
    webui_logger.propagate = False
    webui_logger.addHandler(file_handlers["webui"])
    webui_logger.addHandler(console_handler)
    
    # SmartTub API logs go ONLY to smarttub.log
    api_logger = logging.getLogger("smarttub.api")
    api_logger.setLevel(min_level)
    api_logger.propagate = False
    api_logger.addHandler(file_handlers["smarttub"])
    api_logger.addHandler(console_handler)
    
    # Core logs go ONLY to smarttub.log
    core_logger = logging.getLogger("smarttub.core")
    core_logger.setLevel(min_level)
    core_logger.propagate = False
    core_logger.addHandler(file_handlers["smarttub"])
    core_logger.addHandler(console_handler)
    
    # Uvicorn loggers go ONLY to webui.log
    # Uvicorn uses its own loggers: uvicorn, uvicorn.access, uvicorn.error
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.setLevel(min_level)
    uvicorn_logger.propagate = False
    uvicorn_logger.addHandler(file_handlers["webui"])
    uvicorn_logger.addHandler(console_handler)
    
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.setLevel(min_level)
    uvicorn_access_logger.propagate = False
    uvicorn_access_logger.addHandler(file_handlers["webui"])
    uvicorn_access_logger.addHandler(console_handler)
    
    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    uvicorn_error_logger.setLevel(min_level)
    uvicorn_error_logger.propagate = False
    uvicorn_error_logger.addHandler(file_handlers["webui"])
    uvicorn_error_logger.addHandler(console_handler)


__all__ = ["configure_log_bridge", "CommandAuditLogger"]