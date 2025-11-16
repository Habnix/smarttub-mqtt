"""Resilient MQTT broker client wrapper around :mod:`paho.mqtt`.

This module provides the ``MQTTBrokerClient`` used throughout the application to
establish resilient connections to the configured MQTT broker. It is purposely
minimal for now – it focuses on connection lifecycle and exponential backoff
behaviour as required by foundational task T010. Additional behaviour (topic
management, structured logging, etc.) will build upon this foundation in later
tasks.
"""

from __future__ import annotations

import json
import logging
import time
import types
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from src.core.config_loader import AppConfig

try:  # pragma: no cover - fallback when dependency missing
    import paho.mqtt.client as mqtt  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - tests will patch these symbols
    mqtt = types.SimpleNamespace(  # type: ignore[var-annotated]
        Client=None,
        CallbackAPIVersion=types.SimpleNamespace(VERSION1=1, VERSION2=2),
    )

# Import ErrorTracker if available (T058)
try:
    from src.core.error_tracker import ErrorTracker, ErrorCategory, ErrorSeverity

    HAS_ERROR_TRACKER = True
except ImportError:
    HAS_ERROR_TRACKER = False
    ErrorTracker = None  # type: ignore
    ErrorCategory = None  # type: ignore
    ErrorSeverity = None  # type: ignore


class MQTTBrokerClient:
    """Wrapper that configures and manages a paho-mqtt client instance."""

    DEFAULT_RECONNECT_MIN_SECONDS = 1
    DEFAULT_RECONNECT_MAX_SECONDS = 60
    DEFAULT_KEEPALIVE_SECONDS = 60

    def __init__(
        self,
        config: AppConfig,
        *,
        logger: logging.Logger | None = None,
        error_tracker: Any | None = None,
    ) -> None:
        self._config = config
        self._logger = logger or logging.getLogger("smarttub.mqtt.broker")
        self._error_tracker = error_tracker
        self._client: Any | None = None
        self._loop_started = False
        self._current_backoff = self._reconnect_min
        self._connected = False

        # Topic callback registry for supporting multiple subscriptions
        self._topic_callbacks: dict[str, callable] = {}

        # Meta-topic tracking (T055)
        self._connect_time: float | None = None
        self._disconnect_time: float | None = None
        self._reconnect_count: int = 0
        self._last_error: str | None = None
        self._last_error_time: float | None = None
        self._error_count: int = 0
        self._meta_topic: str | None = None
        self._errors_meta_topic: str | None = None  # T058

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def connect(self) -> None:
        """Create the MQTT client, apply configuration, and connect."""

        client = self._client or self._create_client()
        self._client = client

        if hasattr(client, "reconnect_delay_set"):
            client.reconnect_delay_set(
                min_delay=self._reconnect_min, max_delay=self._reconnect_max
            )

        host, port = self._resolve_endpoint(self._mqtt_config.broker_url)
        keepalive = getattr(
            self._mqtt_config, "keepalive_seconds", self.DEFAULT_KEEPALIVE_SECONDS
        )

        self._current_backoff = self._reconnect_min

        # Try to connect and log helpful diagnostics on failure.
        try:
            self._logger.info(
                "Attempting MQTT connect",
                extra={"host": host, "port": port, "keepalive": keepalive},
            )
            client.connect(host, port, keepalive=keepalive)
        except Exception as exc:  # pragma: no cover - runtime networking
            # Provide an explicit error with resolved host/port to help debugging
            self._logger.error(
                "Failed to connect to MQTT broker",
                exc_info=exc,
                extra={"host": host, "port": port},
            )
            raise

        if not self._loop_started and hasattr(client, "loop_start"):
            client.loop_start()
            self._loop_started = True

    def disconnect(self) -> None:
        """Disconnect gracefully from the MQTT broker."""

        if not self._client:
            return

        if self._loop_started and hasattr(self._client, "loop_stop"):
            try:
                self._client.loop_stop()
            finally:
                self._loop_started = False

        if hasattr(self._client, "disconnect"):
            self._client.disconnect()

        self._connected = False

    def publish(
        self,
        topic: str,
        payload: Any = None,
        *,
        qos: int | None = None,
        retain: bool | None = None,
    ) -> Any:
        """Publish a message via the underlying paho client."""

        if not self._client:
            raise RuntimeError("MQTT client is not connected")

        publish_kwargs: dict[str, Any] = {}
        if qos is not None:
            publish_kwargs["qos"] = qos
        if retain is not None:
            publish_kwargs["retain"] = retain

        # Attempt publish and log details to assist debugging (topic, payload size, qos, retain)
        try:
            # Send the publish through the underlying client
            result = self._client.publish(topic, payload, **publish_kwargs)

            # Compute payload length defensively
            try:
                payload_len = len(payload) if payload is not None else 0
            except Exception:
                payload_len = None

            self._logger.info(
                "mqtt-publish",
                extra={
                    "topic": topic,
                    "payload_len": payload_len,
                    "qos": publish_kwargs.get("qos"),
                    "retain": publish_kwargs.get("retain"),
                },
            )

            return result
        except Exception as exc:  # pragma: no cover - runtime networking
            # Track publish errors (T055)
            self._last_error = f"Publish failed: {str(exc)}"
            self._last_error_time = time.time()
            self._error_count += 1

            # Track in Error Tracker if available (T058)
            if self._error_tracker and HAS_ERROR_TRACKER:
                self._error_tracker.track_error(
                    category=ErrorCategory.MQTT_PUBLISH,
                    message=f"Failed to publish to topic {topic}: {str(exc)}",
                    severity=ErrorSeverity.ERROR,
                    error_code="MQTT_PUBLISH_FAILED",
                    details={"topic": topic},
                )
                # Publish updated error meta (avoid recursion by checking topic)
                if not topic.endswith("/meta/errors"):
                    try:
                        self.publish_meta_errors()
                    except Exception:
                        pass  # Avoid cascading errors

            self._logger.error(
                "mqtt-publish-failed", exc_info=exc, extra={"topic": topic}
            )
            raise

    def subscribe(self, topic: str, callback: callable, *, qos: int = 1) -> None:
        """Subscribe to an MQTT topic with a callback function.

        Args:
            topic: MQTT topic to subscribe to (supports wildcards like +, #)
            callback: Function to call when message is received (signature: callback(topic, payload))
            qos: Quality of Service level
        """
        if not self._client:
            raise RuntimeError("MQTT client is not connected")

        # Register callback for this topic pattern
        self._topic_callbacks[topic] = callback

        # Set up global message handler if not already set
        if not hasattr(self._client, "_message_handler_installed"):

            def on_message(client, userdata, message):
                try:
                    payload = (
                        message.payload.decode("utf-8")
                        if isinstance(message.payload, bytes)
                        else message.payload
                    )
                    received_topic = message.topic

                    # Find the most specific matching callback
                    # Sort by pattern specificity (more path parts = more specific)
                    best_callback = None
                    best_specificity = -1

                    for pattern, cb in self._topic_callbacks.items():
                        if self._topic_matches(pattern, received_topic):
                            # Count non-wildcard parts as specificity score
                            specificity = sum(
                                1
                                for part in pattern.split("/")
                                if part not in ("+", "#")
                            )
                            if specificity > best_specificity:
                                # Prefer more specific patterns
                                best_callback = cb
                                best_specificity = specificity

                    if best_callback:
                        try:
                            best_callback(received_topic, payload)
                        except Exception as e:
                            self._logger.error(
                                f"Error in MQTT callback for topic {received_topic}: {e}",
                                exc_info=True,
                            )
                    else:
                        self._logger.debug(
                            f"No callback matched for topic: {received_topic}"
                        )
                except Exception as e:
                    self._logger.error(
                        f"Error in MQTT message handler: {e}", exc_info=True
                    )

            self._client.on_message = on_message
            self._client._message_handler_installed = True

        self._client.subscribe(topic, qos)
        self._logger.debug(f"Subscribed to MQTT topic: {topic}")

    def _topic_matches(self, pattern: str, topic: str) -> bool:
        """Check if a topic matches a subscription pattern with wildcards.

        Args:
            pattern: Subscription pattern (may contain + or # wildcards)
            topic: Actual topic to match

        Returns:
            True if topic matches pattern
        """
        pattern_parts = pattern.split("/")
        topic_parts = topic.split("/")

        # Quick check for exact match
        if pattern == topic:
            return True

        # Check wildcard patterns
        i = 0
        j = 0
        while i < len(pattern_parts) and j < len(topic_parts):
            if pattern_parts[i] == "#":
                # Multi-level wildcard - matches rest of topic
                return True
            elif pattern_parts[i] == "+":
                # Single-level wildcard - matches one level
                i += 1
                j += 1
            elif pattern_parts[i] == topic_parts[j]:
                i += 1
                j += 1
            else:
                return False

        # Both must be fully consumed for a match
        return i == len(pattern_parts) and j == len(topic_parts)

    def publish_meta_mqtt(self) -> None:
        """Publish MQTT connection metadata to meta/mqtt topic (T055).

        Publishes comprehensive connection status, interface information,
        and error tracking to {base_topic}/meta/mqtt as JSON.
        """
        if not self._meta_topic:
            base_topic = (self._mqtt_config.base_topic or "smarttub-mqtt").rstrip("/")
            self._meta_topic = f"{base_topic}/meta/mqtt"

        # Get version information
        from src.core.version import get_version_info

        version_info = get_version_info()

        # Build meta payload
        now = time.time()
        uptime = int(now - self._connect_time) if self._connect_time else 0

        meta_data = {
            "status": "connected"
            if self._connected
            else ("error" if self._last_error else "disconnected"),
            "broker": self._mqtt_config.broker_url,
            "client_id": getattr(self._mqtt_config, "client_id", "smarttub-mqtt"),
            "versions": {
                "smarttub_mqtt": version_info["smarttub_mqtt"],
                "python_smarttub": version_info["python_smarttub"],
            },
            "connection": {
                "connected": self._connected,
                "uptime_seconds": uptime if self._connected else 0,
                "last_connect": self._format_timestamp(self._connect_time),
                "last_disconnect": self._format_timestamp(self._disconnect_time),
                "reconnect_count": self._reconnect_count,
            },
            "interface": {
                "version": "1.0.0",  # Could be extracted from __version__ later
                "protocol": "MQTT 3.1.1",  # paho-mqtt default
                "tls_enabled": getattr(
                    getattr(self._mqtt_config, "tls", None), "enabled", False
                ),
                "keepalive": getattr(
                    self._mqtt_config, "keepalive", self.DEFAULT_KEEPALIVE_SECONDS
                ),
                "qos_default": self._mqtt_config.qos,
            },
            "errors": {
                "last_error": self._last_error,
                "last_error_time": self._format_timestamp(self._last_error_time),
                "error_count": self._error_count,
            },
        }

        try:
            payload = json.dumps(meta_data, indent=None)
            self.publish(self._meta_topic, payload, qos=1, retain=True)
        except Exception as e:
            self._logger.warning(f"Failed to publish MQTT meta topic: {e}")

    @staticmethod
    def _format_timestamp(ts: float | None) -> str | None:
        """Format Unix timestamp to ISO 8601 string."""
        if ts is None:
            return None
        try:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.isoformat()
        except Exception:
            return None

    def publish_meta_errors(self) -> None:
        """Publish error tracking metadata to meta/errors topic (T058).

        Publishes comprehensive error summary and subsystem status
        to {base_topic}/meta/errors as JSON.
        """
        if not self._error_tracker:
            return  # No error tracker available

        if not self._errors_meta_topic:
            base_topic = (self._mqtt_config.base_topic or "smarttub-mqtt").rstrip("/")
            self._errors_meta_topic = f"{base_topic}/meta/errors"

        try:
            # Get error summary from tracker
            error_summary = self._error_tracker.get_error_summary()
            subsystem_status = self._error_tracker.get_subsystem_status()

            # Build comprehensive error meta payload
            error_meta = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": error_summary,
                "subsystems": subsystem_status,
            }

            payload = json.dumps(error_meta, indent=None)
            self.publish(self._errors_meta_topic, payload, qos=1, retain=True)

        except Exception as e:
            self._logger.warning(f"Failed to publish error meta topic: {e}")

    def publish_discovery_progress(self, progress_data: dict) -> None:
        """Publish discovery progress to meta/discovery/progress topic (T059).

        Publishes real-time discovery progress updates including:
        - Overall progress percentage
        - Current spa being probed
        - Component-level progress
        - Example data from discovered components

        Args:
            progress_data: Progress snapshot from DiscoveryProgressTracker
        """
        base_topic = (self._mqtt_config.base_topic or "smarttub-mqtt").rstrip("/")
        progress_topic = f"{base_topic}/meta/discovery/progress"

        try:
            # Add timestamp to progress data
            progress_with_timestamp = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **progress_data,
            }

            payload = json.dumps(progress_with_timestamp, indent=None)
            # Use QoS 0 for frequent progress updates, retain last state
            self.publish(progress_topic, payload, qos=0, retain=True)

        except Exception as e:
            self._logger.warning(f"Failed to publish discovery progress: {e}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @property
    def _mqtt_config(self) -> Any:
        return self._config.mqtt

    @property
    def _reconnect_min(self) -> int:
        return max(
            1,
            int(
                getattr(
                    self._mqtt_config,
                    "reconnect_min_seconds",
                    self.DEFAULT_RECONNECT_MIN_SECONDS,
                )
            ),
        )

    @property
    def _reconnect_max(self) -> int:
        return max(
            self._reconnect_min,
            int(
                getattr(
                    self._mqtt_config,
                    "reconnect_max_seconds",
                    self.DEFAULT_RECONNECT_MAX_SECONDS,
                )
            ),
        )

    def _create_client(self) -> Any:
        client_ctor = getattr(mqtt, "Client", None)
        if client_ctor is None:
            raise RuntimeError("paho-mqtt is required to use MQTTBrokerClient")

        callback_api = getattr(
            getattr(mqtt, "CallbackAPIVersion", None), "VERSION2", None
        )

        # Derive an effective client_id. If the configured client_id is the
        # default ("smarttub-mqtt") or empty, append a process-unique suffix
        # (PID) to avoid accidental collisions when multiple test runs or
        # containers are started on the same host. If the user explicitly set
        # MQTT_CLIENT_ID in the config/env we preserve it unchanged.
        configured_id = getattr(self._mqtt_config, "client_id", None)
        if not configured_id:
            configured_id = "smarttub-mqtt"

        effective_client_id = configured_id
        try:
            # Only modify if it's the default base id to reduce surprise.
            if configured_id == "smarttub-mqtt":
                import os

                effective_client_id = f"{configured_id}-{os.getpid()}"
        except Exception:
            # Fallback: leave configured id unchanged on any error
            effective_client_id = configured_id

        try:
            if callback_api is not None:
                client = client_ctor(callback_api, client_id=effective_client_id)
            else:
                client = client_ctor(client_id=effective_client_id)
        except TypeError:  # pragma: no cover - compatibility path
            client = client_ctor(client_id=effective_client_id)

        if hasattr(client, "enable_logger"):
            client.enable_logger(self._logger)

        if self._mqtt_config.username:
            client.username_pw_set(
                self._mqtt_config.username, self._mqtt_config.password
            )

        tls_cfg = getattr(self._mqtt_config, "tls", None)
        if getattr(tls_cfg, "enabled", False) and hasattr(client, "tls_set"):
            ca_path = getattr(tls_cfg, "ca_cert_path", None) or None
            client.tls_set(ca_certs=ca_path)

        client.on_connect = self._handle_connect
        client.on_disconnect = self._handle_disconnect

        return client

    def _resolve_endpoint(self, broker_url: str) -> tuple[str, int]:
        parsed = urlparse(broker_url or "")

        if parsed.scheme:
            host = parsed.hostname or "localhost"
            if parsed.port is not None:
                port = parsed.port
            elif parsed.scheme in {"mqtts", "ssl", "tls"}:
                port = 8883
            else:
                port = 1883
            return host, port

        # Fallback for host[:port] without scheme
        host_port = broker_url.split(":", maxsplit=1)
        host = host_port[0] if host_port[0] else "localhost"
        if len(host_port) == 2:
            try:
                port = int(host_port[1])
            except ValueError:
                port = 1883
        else:
            port = 1883
        return host, port

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def _handle_connect(
        self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any
    ) -> None:
        self._current_backoff = self._reconnect_min
        self._connected = True
        self._connect_time = time.time()

        # Increment reconnect count (first connect is 0, subsequent reconnects are 1, 2, ...)
        if self._disconnect_time is not None:
            self._reconnect_count += 1

        # Try to extract a stable client identifier for debugging (paho exposes
        # either `client_id` or `_client_id`, often bytes). Decode if needed.
        client_id = None
        try:
            raw_id = getattr(client, "client_id", None) or getattr(
                client, "_client_id", None
            )
            if isinstance(raw_id, (bytes, bytearray)):
                try:
                    client_id = raw_id.decode("utf-8", errors="ignore")
                except Exception:
                    client_id = str(raw_id)
            else:
                client_id = str(raw_id) if raw_id is not None else None
        except Exception:
            client_id = None

        self._logger.info(
            "Connected to MQTT broker",
            extra={
                "reason_code": getattr(reason_code, "value", reason_code),
                "client_id": client_id,
                "flags": flags,
                "properties": properties,
            },
        )

        # Resubscribe to all topics after (re)connect
        if self._topic_callbacks:
            self._logger.info(
                f"Resubscribing to {len(self._topic_callbacks)} MQTT topics after connect"
            )
            for topic in self._topic_callbacks.keys():
                try:
                    client.subscribe(topic, qos=1)
                    self._logger.debug(f"Resubscribed to: {topic}")
                except Exception as e:
                    self._logger.error(f"Failed to resubscribe to {topic}: {e}")

        # Publish meta/mqtt topic (T055)
        try:
            self.publish_meta_mqtt()
        except Exception as e:
            self._logger.warning(f"Failed to publish MQTT meta on connect: {e}")

    def _handle_disconnect(
        self,
        client: Any,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        self._disconnect_time = time.time()
        failure = self._reason_is_failure(reason_code)

        if not failure:
            self._current_backoff = self._reconnect_min
            self._connected = False
            # Log clean disconnect with helpful metadata
            client_id = None
            try:
                raw_id = getattr(client, "client_id", None) or getattr(
                    client, "_client_id", None
                )
                if isinstance(raw_id, (bytes, bytearray)):
                    try:
                        client_id = raw_id.decode("utf-8", errors="ignore")
                    except Exception:
                        client_id = str(raw_id)
                else:
                    client_id = str(raw_id) if raw_id is not None else None
            except Exception:
                client_id = None

            self._logger.debug(
                "MQTT client disconnected cleanly",
                extra={
                    "client_id": client_id,
                    "disconnect_flags": disconnect_flags,
                    "properties": properties,
                },
            )

            # Publish meta/mqtt with disconnected status
            try:
                self.publish_meta_mqtt()
            except Exception as e:
                self._logger.debug(
                    f"Failed to publish MQTT meta on clean disconnect: {e}"
                )

            return

        # Failure path: track error and include additional metadata
        self._error_count += 1
        reason_value = getattr(reason_code, "value", reason_code)
        self._last_error = f"Connection lost (reason: {reason_value})"
        self._last_error_time = time.time()

        # Track in Error Tracker if available (T058)
        if self._error_tracker and HAS_ERROR_TRACKER:
            self._error_tracker.track_error(
                category=ErrorCategory.MQTT_CONNECTION,
                message=f"MQTT connection lost: {reason_value}",
                severity=ErrorSeverity.WARNING,
                error_code="MQTT_CONNECTION_LOST",
                details={"reason_code": reason_value},
            )

        client_id = None
        try:
            raw_id = getattr(client, "client_id", None) or getattr(
                client, "_client_id", None
            )
            if isinstance(raw_id, (bytes, bytearray)):
                try:
                    client_id = raw_id.decode("utf-8", errors="ignore")
                except Exception:
                    client_id = str(raw_id)
            else:
                client_id = str(raw_id) if raw_id is not None else None
        except Exception:
            client_id = None

        delay = self._current_backoff
        self._logger.warning(
            "MQTT connection lost; scheduling reconnect",
            extra={
                "delay_seconds": delay,
                "reason_code": reason_value,
                "client_id": client_id,
                "disconnect_flags": disconnect_flags,
                "properties": properties,
            },
        )

        time.sleep(delay)

        try:
            client.reconnect()
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.warning("MQTT reconnect attempt failed", exc_info=exc)
            self._last_error = f"Reconnect failed: {str(exc)}"
            self._last_error_time = time.time()
            self._error_count += 1

            # Track in Error Tracker if available (T058)
            if self._error_tracker and HAS_ERROR_TRACKER:
                self._error_tracker.track_error(
                    category=ErrorCategory.MQTT_CONNECTION,
                    message=f"MQTT reconnect failed: {str(exc)}",
                    severity=ErrorSeverity.ERROR,
                    error_code="MQTT_RECONNECT_FAILED",
                )

        self._current_backoff = min(self._current_backoff * 2, self._reconnect_max)
        self._connected = False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    @staticmethod
    def _reason_is_failure(reason_code: Any) -> bool:
        if hasattr(reason_code, "is_failure"):
            return bool(reason_code.is_failure)

        candidate = getattr(reason_code, "value", reason_code)
        try:
            return int(candidate) != 0
        except (TypeError, ValueError):
            return bool(candidate)


__all__ = ["MQTTBrokerClient", "mqtt", "time"]
