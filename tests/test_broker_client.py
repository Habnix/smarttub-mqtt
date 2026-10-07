"""Regression tests for MQTT reconnect handling."""

import asyncio
from types import SimpleNamespace

import pytest

from src.mqtt.broker_client import MQTTBrokerClient


class _FakeClient:
    def __init__(
        self, *, fail_messages: bool = False, fail_connect: bool = False
    ) -> None:
        self.fail_messages = fail_messages
        self.fail_connect = fail_connect
        self.disconnect_event = asyncio.Event()
        self.subscriptions: list[tuple[str, int]] = []
        self.closed = False
        self.block_publishes = False
        self.release_publishes = asyncio.Event()
        self.publish_calls = 0
        self.active_publishes = 0
        self.max_active_publishes = 0
        self.published: list[tuple[tuple, dict]] = []

    async def __aenter__(self):
        if self.fail_connect:
            raise ConnectionError("broker unavailable")
        return self

    async def __aexit__(self, *_args):
        self.closed = True

    @property
    def messages(self):
        return self._messages()

    async def _messages(self):
        await self.disconnect_event.wait()
        if self.fail_messages:
            raise ConnectionError("broker connection lost")
        if False:  # pragma: no cover - makes this function an async generator
            yield None

    async def subscribe(self, topic: str, *, qos: int):
        self.subscriptions.append((topic, qos))

    async def unsubscribe(self, _topic: str):
        return None

    async def publish(self, *_args, **_kwargs):
        self.published.append((_args, _kwargs))
        self.publish_calls += 1
        self.active_publishes += 1
        self.max_active_publishes = max(
            self.max_active_publishes, self.active_publishes
        )
        try:
            if self.block_publishes:
                await self.release_publishes.wait()
        finally:
            self.active_publishes -= 1


def _config():
    return SimpleNamespace(
        mqtt=SimpleNamespace(
            broker_url="mqtt://broker:1883",
            username=None,
            password=None,
            client_id="smarttub-test",
            qos=1,
            retain=True,
            keepalive=60,
            tls=SimpleNamespace(enabled=False, ca_cert_path=""),
        )
    )


@pytest.mark.asyncio
async def test_reconnect_restores_subscriptions(monkeypatch):
    """An unexpected message-loop exit reconnects and resubscribes topics."""
    first = _FakeClient(fail_messages=True)
    second = _FakeClient()
    clients = iter((first, second))

    broker = MQTTBrokerClient(_config())
    broker.DEFAULT_RECONNECT_MIN_SECONDS = 0.01
    broker.DEFAULT_RECONNECT_MAX_SECONDS = 0.02
    monkeypatch.setattr(broker, "_create_client", lambda: next(clients))

    await broker.connect()
    await broker.subscribe("smarttub/commands/#", lambda *_args: None, qos=1)

    first.disconnect_event.set()

    async def wait_for_reconnect():
        while not second.subscriptions:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait_for_reconnect(), timeout=1)

    assert broker.is_connected
    assert second.subscriptions == [("smarttub/commands/#", 1)]
    assert broker.get_connection_stats()["reconnect_count"] == 2

    await broker.disconnect()
    assert second.closed


@pytest.mark.asyncio
async def test_initial_broker_failure_starts_degraded_and_recovers(monkeypatch):
    first = _FakeClient(fail_connect=True)
    second = _FakeClient()
    clients = iter((first, second))
    broker = MQTTBrokerClient(_config())
    broker.DEFAULT_RECONNECT_MIN_SECONDS = 0.01
    broker.DEFAULT_RECONNECT_MAX_SECONDS = 0.02
    monkeypatch.setattr(broker, "_create_client", lambda: next(clients))

    await broker.connect(allow_degraded=True)
    assert not broker.is_connected
    await broker.subscribe("smarttub/commands/#", lambda *_args: None, qos=1)
    broker.publish_sync("smarttub/status", "degraded", retain=True)

    async def wait_for_recovery():
        while not second.subscriptions or second.publish_calls < 1:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait_for_recovery(), timeout=1)

    assert broker.is_connected
    assert second.subscriptions == [("smarttub/commands/#", 1)]
    assert second.published[0][1]["payload"] == "degraded"
    await broker.disconnect()


@pytest.mark.asyncio
async def test_publish_sync_buffers_retained_messages_while_disconnected(caplog):
    """Offline retained snapshots are coalesced instead of silently lost."""
    broker = MQTTBrokerClient(_config())

    broker.publish_sync("smarttub/state", "first", retain=True)
    broker.publish_sync("smarttub/state", "latest", retain=True)
    await asyncio.sleep(0)

    stats = broker.get_buffer_stats()
    assert stats["size"] == 1
    assert stats["messages_coalesced"] == 1
    assert "buffering retained/critical messages" in caplog.text


@pytest.mark.asyncio
async def test_connect_flushes_latest_retained_and_all_critical_results(monkeypatch):
    client = _FakeClient()
    config = _config()
    config.mqtt.publish_queue_size = 10
    broker = MQTTBrokerClient(config)
    monkeypatch.setattr(broker, "_create_client", lambda: client)

    broker.publish_sync("smarttub/spa/state", "old", retain=True)
    broker.publish_sync("smarttub/spa/state", "latest", retain=True)
    broker.publish_sync("smarttub/spa/commands/result", "accepted", retain=False)
    broker.publish_sync("smarttub/spa/commands/result", "sent", retain=False)

    await broker.connect()
    try:

        async def wait_for_flush():
            while client.publish_calls < 3:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_for_flush(), timeout=1)
        payloads = [kwargs["payload"] for _args, kwargs in client.published]
        assert payloads == ["accepted", "sent", "latest"]
        assert broker.get_buffer_stats()["size"] == 0
    finally:
        await broker.disconnect()


@pytest.mark.asyncio
async def test_publish_sync_limits_concurrent_broker_calls(monkeypatch):
    """A snapshot burst is handled by a bounded publish worker pool."""
    client = _FakeClient()
    client.block_publishes = True
    broker = MQTTBrokerClient(_config())
    broker.PUBLISH_CONCURRENCY = 2
    monkeypatch.setattr(broker, "_create_client", lambda: client)

    await broker.connect()
    try:
        for index in range(6):
            broker.publish_sync(f"smarttub/state/{index}", "value")

        async def wait_for_workers():
            while client.active_publishes < 2:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_for_workers(), timeout=1)
        assert client.max_active_publishes == 2

        client.release_publishes.set()

        async def wait_for_all_publishes():
            while client.publish_calls < 6:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_for_all_publishes(), timeout=1)
        assert client.max_active_publishes == 2
    finally:
        client.release_publishes.set()
        await broker.disconnect()
