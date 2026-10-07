"""Application MQTT client built directly on top of :mod:`aiomqtt`.

The rest of the application uses a small wrapper rather than depending on the
MQTT library directly.  This keeps configuration, error tracking and callback
dispatch in one place while using aiomqtt's native asyncio API underneath.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import ssl
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from contextlib import suppress
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlparse

import aiomqtt

from src.core.config_loader import AppConfig

try:
    from src.core.error_tracker import ErrorCategory, ErrorSeverity

    HAS_ERROR_TRACKER = True
except ImportError:  # pragma: no cover - defensive import for partial installs
    ErrorCategory = None  # type: ignore[assignment,misc]
    ErrorSeverity = None  # type: ignore[assignment,misc]
    HAS_ERROR_TRACKER = False


class MQTTBrokerClient:
    """Async MQTT client wrapper used by the application.

    ``aiomqtt`` exposes incoming messages through an async iterator.  A single
    task consumes that iterator and dispatches each message to the most
    specific registered subscription callback, preserving the callback API
    used by the application.
    """

    DEFAULT_KEEPALIVE_SECONDS = 60
    DEFAULT_RECONNECT_MIN_SECONDS = 1
    DEFAULT_RECONNECT_MAX_SECONDS = 60
    PUBLISH_CONCURRENCY = 8

    def __init__(
        self,
        config: AppConfig,
        *,
        logger: logging.Logger | None = None,
        error_tracker: Any | None = None,
    ) -> None:
        self._app_config = config
        self._logger = logger or logging.getLogger("smarttub.mqtt.broker")
        self._error_tracker = error_tracker
        self._client: aiomqtt.Client | None = None
        self._message_task: asyncio.Task[None] | None = None
        self._topic_callbacks: dict[str, tuple[Callable[..., Any], int]] = {}
        self._connected = False
        self._reconnect_task: asyncio.Task[None] | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._offline_publish_warned = False
        self._publish_queue: (
            asyncio.Queue[tuple[str, Any, int | None, bool | None]] | None
        ) = None
        self._publish_workers: list[asyncio.Task[None]] = []
        self._offline_retained: OrderedDict[
            str, tuple[str, Any, int | None, bool | None]
        ] = OrderedDict()
        self._offline_critical: deque[tuple[str, Any, int | None, bool | None]] = (
            deque()
        )
        self._messages_buffered = 0
        self._messages_dropped = 0
        self._messages_coalesced = 0

        self._connect_time: float | None = None
        self._disconnect_time: float | None = None
        self._reconnect_count = 0
        self._last_error: str | None = None
        self._error_count = 0

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, *, allow_degraded: bool = False) -> None:
        """Connect and optionally keep retrying after an initial failure."""
        if self._connected:
            return

        if self._shutdown_event is None:
            self._shutdown_event = asyncio.Event()
        self._shutdown_event.clear()

        try:
            await self._connect_once()
        except Exception:
            if not allow_degraded:
                raise
            self._logger.warning(
                "Starting with MQTT unavailable; reconnect will continue in background"
            )
        self._start_publish_workers()
        self._flush_offline_buffer()
        self._reconnect_task = asyncio.create_task(
            self._connection_monitor(), name="smarttub-mqtt-reconnect"
        )

    async def _connect_once(self) -> None:
        """Establish one MQTT connection and start its message consumer."""
        client = self._create_client()
        client_entered = False
        try:
            # aiomqtt 2.x manages the network connection through its async
            # context manager; Client.connect()/disconnect() do not exist.
            await client.__aenter__()
            client_entered = True
            self._client = client
            self._connected = True
            self._connect_time = time.monotonic()
            self._reconnect_count += 1
            self._offline_publish_warned = False
            self._message_task = asyncio.create_task(
                self._consume_messages(), name="smarttub-mqtt-messages"
            )
            host, port, _ = self._broker_endpoint()
            self._logger.info(f"Connected to MQTT broker {host}:{port}")
        except Exception as exc:
            if client_entered:
                with suppress(Exception):
                    await client.__aexit__(type(exc), exc, exc.__traceback__)
            self._record_error("connection", exc)
            self._logger.error(f"Failed to connect to MQTT broker: {exc}")
            raise

    async def _connection_monitor(self) -> None:
        """Reconnect after an unexpected disconnect using exponential backoff."""
        shutdown_event = self._require_shutdown_event()

        while not shutdown_event.is_set():
            if self._connected:
                message_task = self._message_task
                if message_task is None:
                    self._connected = False
                else:
                    try:
                        await message_task
                    except asyncio.CancelledError:
                        if shutdown_event.is_set():
                            return

                if shutdown_event.is_set():
                    return

                self._connected = False
                self._disconnect_time = time.monotonic()
                self._logger.warning("MQTT connection lost; starting reconnect loop")
                await self._close_current_client()

            delay = self.DEFAULT_RECONNECT_MIN_SECONDS
            while not shutdown_event.is_set():
                self._logger.info(f"Attempting MQTT reconnect in {delay} seconds")
                if await self._wait_for_shutdown(delay):
                    return

                try:
                    await self._connect_once()
                    await self._restore_subscriptions()
                    self._flush_offline_buffer()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    await self._close_current_client()
                    self._logger.warning(
                        f"MQTT reconnect attempt failed: {exc}; retrying with backoff",
                    )
                    delay = min(delay * 2, self.DEFAULT_RECONNECT_MAX_SECONDS)
                    continue

                host, port, _ = self._broker_endpoint()
                self._logger.info(
                    f"Reconnected to MQTT broker {host}:{port}; "
                    f"restored {len(self._topic_callbacks)} subscriptions"
                )
                break

    async def _restore_subscriptions(self) -> None:
        """Restore all registered subscriptions after reconnecting."""
        client = self._require_client()
        for topic, (_callback, qos) in self._topic_callbacks.items():
            try:
                await client.subscribe(topic, qos=qos)
            except Exception as exc:
                self._record_error("subscribe", exc, topic=topic)
                raise

    async def _wait_for_shutdown(self, delay: float) -> bool:
        """Wait for the retry delay, returning whether shutdown was requested."""
        shutdown_event = self._require_shutdown_event()
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=delay)
        except TimeoutError:
            return False
        return True

    def _require_shutdown_event(self) -> asyncio.Event:
        if self._shutdown_event is None:
            raise RuntimeError("MQTT connection lifecycle is not initialized")
        return self._shutdown_event

    async def disconnect(self) -> None:
        """Stop message processing and disconnect gracefully."""
        if self._shutdown_event is not None:
            self._shutdown_event.set()

        reconnect_task = self._reconnect_task
        self._reconnect_task = None
        if reconnect_task is not None and reconnect_task is not asyncio.current_task():
            reconnect_task.cancel()
            with suppress(asyncio.CancelledError):
                await reconnect_task

        await self._stop_publish_workers(drain=self._connected)
        await self._close_current_client()
        self._connected = False
        self._disconnect_time = time.monotonic()

    async def _close_current_client(self) -> None:
        """Cancel the current message consumer and close its MQTT context."""
        task = self._message_task
        self._message_task = None
        current_task = asyncio.current_task()
        if task is not None and task is not current_task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        client: Any = self._client
        self._client = None
        self._connected = False
        if client is not None:
            try:
                # aiomqtt 2.x disconnects when leaving its async context.
                await client.__aexit__(None, None, None)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning(f"Error during MQTT disconnect: {exc}")

    # ------------------------------------------------------------------
    # Publishing and subscriptions
    # ------------------------------------------------------------------

    async def publish(
        self,
        topic: str,
        payload: Any,
        *,
        qos: int | None = None,
        retain: bool | None = None,
    ) -> None:
        """Publish a message, serializing non-string payloads as JSON."""
        client = self._require_client()
        if not isinstance(payload, (str, bytes, bytearray, memoryview)):
            payload = json.dumps(payload)

        effective_qos = self._app_config.mqtt.qos if qos is None else qos
        effective_retain = self._app_config.mqtt.retain if retain is None else retain
        try:
            await client.publish(
                topic,
                payload=payload,
                qos=effective_qos,
                retain=effective_retain,
            )
            self._logger.debug(f"Published MQTT message to {topic}")
        except Exception as exc:
            self._record_error("publish", exc, topic=topic)
            if self._is_connection_error(exc):
                self._signal_connection_loss()
                if not self._offline_publish_warned:
                    self._logger.warning(
                        f"MQTT publish interrupted for {topic}; waiting for reconnect"
                    )
                    self._offline_publish_warned = True
            else:
                self._logger.error(f"Failed to publish to {topic}: {exc}")
            raise

    def publish_sync(
        self,
        topic: str,
        payload: Any,
        qos: int | None = None,
        retain: bool | None = None,
    ) -> None:
        """Schedule :meth:`publish` for synchronous logging/callback code."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._logger.warning(
                f"Cannot publish to {topic} synchronously: no event loop is running",
            )
            return

        if not self._connected:
            self._buffer_publish((topic, payload, qos, retain))
            return

        if self._publish_queue is None:
            self._logger.warning(
                f"Skipping MQTT publish to {topic}: publish queue is unavailable"
            )
            return

        self._enqueue_publish((topic, payload, qos, retain))

    def _enqueue_publish(self, item: tuple[str, Any, int | None, bool | None]) -> None:
        """Enqueue one publish or apply the documented overflow policy."""
        if self._publish_queue is None:
            self._buffer_publish(item)
            return
        try:
            self._publish_queue.put_nowait(item)
        except asyncio.QueueFull:
            self._buffer_publish(item)

    def _buffer_publish(self, item: tuple[str, Any, int | None, bool | None]) -> None:
        """Keep latest retained values and bounded critical command results."""
        topic, _payload, _qos, retain = item
        effective_retain = self._app_config.mqtt.retain if retain is None else retain
        capacity = getattr(self._app_config.mqtt, "publish_queue_size", 1000)
        if effective_retain:
            if topic in self._offline_retained:
                self._messages_coalesced += 1
                self._offline_retained.pop(topic)
            elif len(self._offline_retained) >= capacity:
                self._offline_retained.popitem(last=False)
                self._messages_dropped += 1
            self._offline_retained[topic] = item
            self._messages_buffered += 1
        elif topic.endswith("/commands/result"):
            if len(self._offline_critical) >= capacity:
                self._offline_critical.popleft()
                self._messages_dropped += 1
            self._offline_critical.append(item)
            self._messages_buffered += 1
        else:
            self._messages_dropped += 1
        if not self._offline_publish_warned:
            self._logger.warning(
                "MQTT unavailable or publish queue full; buffering retained/critical messages"
            )
            self._offline_publish_warned = True

    def _flush_offline_buffer(self) -> None:
        """Move buffered messages back to the bounded worker queue."""
        if self._publish_queue is None or not self._connected:
            return
        pending = list(self._offline_critical) + list(self._offline_retained.values())
        self._offline_critical.clear()
        self._offline_retained.clear()
        for index, item in enumerate(pending):
            try:
                self._publish_queue.put_nowait(item)
            except asyncio.QueueFull:
                for remaining in pending[index:]:
                    self._buffer_publish(remaining)
                break

    def _start_publish_workers(self) -> None:
        """Create a bounded worker pool for fire-and-forget publishes."""
        if self._publish_workers:
            return

        queue_size = getattr(self._app_config.mqtt, "publish_queue_size", 1000)
        self._publish_queue = asyncio.Queue(maxsize=queue_size)
        self._publish_workers = [
            asyncio.create_task(
                self._publish_worker(), name=f"smarttub-mqtt-publish-worker:{index}"
            )
            for index in range(self.PUBLISH_CONCURRENCY)
        ]

    async def _stop_publish_workers(self, *, drain: bool = True) -> None:
        """Drain briefly, then cancel the publish worker pool during shutdown."""
        workers = self._publish_workers
        self._publish_workers = []
        publish_queue = self._publish_queue
        if drain and publish_queue is not None and workers:
            timeout = getattr(self._app_config.mqtt, "publish_drain_timeout_seconds", 5)
            try:
                await asyncio.wait_for(publish_queue.join(), timeout=timeout)
            except TimeoutError:
                self._logger.warning(
                    "MQTT publish queue did not drain within %s seconds", timeout
                )
        for worker in workers:
            worker.cancel()
        for worker in workers:
            with suppress(asyncio.CancelledError):
                await worker
        if publish_queue is not None:
            while True:
                try:
                    item = publish_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                self._buffer_publish(item)
                publish_queue.task_done()
        self._publish_queue = None

    async def _publish_worker(self) -> None:
        """Publish queued messages while bounding concurrent broker calls."""
        queue = self._publish_queue
        if queue is None:  # pragma: no cover - only possible during shutdown
            return

        while True:
            topic, payload, qos, retain = await queue.get()
            try:
                if not self._connected:
                    self._buffer_publish((topic, payload, qos, retain))
                    continue
                await self.publish(topic, payload, qos=qos, retain=retain)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                if self._is_connection_error(exc):
                    self._buffer_publish((topic, payload, qos, retain))
                else:
                    self._logger.error(f"Background MQTT publish failed: {exc}")
            finally:
                queue.task_done()
                if self._connected:
                    self._flush_offline_buffer()

    async def subscribe(
        self,
        topic: str,
        callback: Callable[..., Any],
        *,
        qos: int = 1,
    ) -> None:
        """Subscribe and register a callback for messages matching ``topic``."""
        previous = self._topic_callbacks.get(topic)
        self._topic_callbacks[topic] = (callback, qos)
        if not self._connected or self._client is None:
            self._logger.info(
                "Registered MQTT subscription for activation after reconnect: %s",
                topic,
            )
            return
        client = self._client
        try:
            await client.subscribe(topic, qos=qos)
        except Exception as exc:
            if previous is None:
                self._topic_callbacks.pop(topic, None)
            else:
                self._topic_callbacks[topic] = previous
            self._record_error("subscribe", exc, topic=topic)
            raise
        self._logger.debug(f"Subscribed to MQTT topic {topic}")

    async def unsubscribe(self, topic: str) -> None:
        """Remove a subscription and its callback."""
        self._topic_callbacks.pop(topic, None)
        if not self._connected or self._client is None:
            return
        await self._client.unsubscribe(topic)
        self._logger.debug(f"Unsubscribed from MQTT topic {topic}")

    async def _consume_messages(self) -> None:
        """Dispatch messages received from aiomqtt's async message iterator."""
        client = self._client
        if client is None:
            return

        try:
            async for message in client.messages:
                topic = str(message.topic)
                callback = self._find_callback(topic)
                if callback is None:
                    self._logger.debug(f"No callback matched MQTT topic {topic}")
                    continue
                try:
                    result = callback(topic, message.payload)
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    self._logger.exception(f"Error in MQTT callback for topic {topic}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            if self._connected:
                self._record_error("connection", exc)
                self._logger.error(f"MQTT message loop stopped: {exc}")
            self._signal_connection_loss()

    # ------------------------------------------------------------------
    # Introspection and helpers
    # ------------------------------------------------------------------

    def get_connection_stats(self) -> dict[str, Any]:
        """Return connection statistics compatible with the former wrapper."""
        uptime = 0
        if self._connected and self._connect_time is not None:
            uptime = max(0, int(time.monotonic() - self._connect_time))
        return {
            "connected": self._connected,
            "uptime_seconds": uptime,
            "reconnect_count": self._reconnect_count,
            "error_count": self._error_count,
            "last_error": self._last_error,
            "connect_time": self._connect_time,
            "disconnect_time": self._disconnect_time,
        }

    def get_buffer_stats(self) -> dict[str, Any]:
        """Return bounded publish queue and offline-buffer statistics."""
        queued = self._publish_queue.qsize() if self._publish_queue is not None else 0
        buffered = len(self._offline_retained) + len(self._offline_critical)
        capacity = getattr(self._app_config.mqtt, "publish_queue_size", 1000)
        return {
            "size": queued + buffered,
            "capacity": capacity * 3,
            "utilization_percent": min(
                100.0, ((queued + buffered) / (capacity * 3)) * 100
            ),
            "messages_buffered": self._messages_buffered,
            "messages_dropped": self._messages_dropped,
            "messages_coalesced": self._messages_coalesced,
        }

    @property
    def is_connected(self) -> bool:
        """Whether the aiomqtt client is currently connected."""
        return self._connected

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.disconnect()

    def _create_client(self) -> aiomqtt.Client:
        host, port, scheme = self._broker_endpoint()
        mqtt_cfg = self._app_config.mqtt
        tls_enabled = mqtt_cfg.tls.enabled or scheme in {"mqtts", "ssl", "tls"}
        tls_context = None
        if tls_enabled:
            tls_context = ssl.create_default_context(
                cafile=mqtt_cfg.tls.ca_cert_path or None
            )

        return aiomqtt.Client(
            hostname=host,
            port=port,
            username=mqtt_cfg.username,
            password=mqtt_cfg.password,
            identifier=mqtt_cfg.client_id or None,
            keepalive=getattr(mqtt_cfg, "keepalive", self.DEFAULT_KEEPALIVE_SECONDS),
            tls_context=tls_context,
        )

    def _broker_endpoint(self) -> tuple[str, int, str]:
        broker_url = self._app_config.mqtt.broker_url
        if "://" not in broker_url:
            broker_url = f"mqtt://{broker_url}"
        parsed = urlparse(broker_url)
        return parsed.hostname or "localhost", parsed.port or 1883, parsed.scheme

    def _require_client(self) -> aiomqtt.Client:
        if self._client is None or not self._connected:
            raise RuntimeError("MQTT client is not connected")
        return self._client

    def _find_callback(self, topic: str) -> Callable[..., Any] | None:
        matches = [
            (pattern, callback_and_qos[0])
            for pattern, callback_and_qos in self._topic_callbacks.items()
            if self._topic_matches(pattern, topic)
        ]
        if not matches:
            return None
        return max(
            matches,
            key=lambda item: sum(part not in {"+", "#"} for part in item[0].split("/")),
        )[1]

    @staticmethod
    def _topic_matches(pattern: str, topic: str) -> bool:
        pattern_parts = pattern.split("/")
        topic_parts = topic.split("/")
        for index, pattern_part in enumerate(pattern_parts):
            if pattern_part == "#":
                return index == len(pattern_parts) - 1
            if index >= len(topic_parts):
                return False
            if pattern_part != "+" and pattern_part != topic_parts[index]:
                return False
        return len(pattern_parts) == len(topic_parts)

    def _record_error(self, category: str, exc: Exception, **details: Any) -> None:
        self._last_error = str(exc)
        self._error_count += 1
        if self._error_tracker is None or not HAS_ERROR_TRACKER:
            return
        category_map = {
            "connection": ErrorCategory.MQTT_CONNECTION,
            "publish": ErrorCategory.MQTT_PUBLISH,
            "subscribe": ErrorCategory.MQTT_CONNECTION,
        }
        try:
            self._error_tracker.track_error(
                category=category_map[category],
                message=str(exc),
                severity=ErrorSeverity.ERROR,
                error_code=f"MQTT_{category.upper()}_FAILED",
                details=details,
            )
        except Exception:
            self._logger.debug("Failed to record MQTT error", exc_info=True)

    def _signal_connection_loss(self) -> None:
        """Mark the transport offline and wake the monitor for reconnection."""
        if not self._connected:
            return

        self._connected = False
        self._disconnect_time = time.monotonic()
        message_task = self._message_task
        if message_task is not None and message_task is not asyncio.current_task():
            message_task.cancel()

    @staticmethod
    def _is_connection_error(exc: BaseException) -> bool:
        """Recognize Paho/aiomqtt errors that indicate the transport is offline."""
        message = str(exc).lower()
        return any(
            f"[code:{code}]" in message for code in (4, 7, 15, 16)
        ) or isinstance(exc, (ConnectionError, TimeoutError))


__all__ = ["MQTTBrokerClient"]
