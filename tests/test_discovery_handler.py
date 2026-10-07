"""Behaviour tests for the MQTT discovery control boundary."""

import asyncio
from types import SimpleNamespace

import pytest

from src.mqtt.discovery_handler import DiscoveryMQTTHandler


class _Coordinator:
    def __init__(self):
        self.publisher = None
        self.status_publications = 0
        self.starts = []
        self.stops = 0

    def set_mqtt_publisher(self, publisher):
        self.publisher = publisher

    async def publish_status_to_mqtt(self):
        self.status_publications += 1

    async def start_discovery(self, *, mode):
        self.starts.append(mode)
        return {"success": True}

    async def stop_discovery(self):
        self.stops += 1
        return {"success": True}


class _MQTTClient:
    def __init__(self):
        self.subscriptions = []
        self.unsubscriptions = []
        self.publications = []

    async def subscribe(self, *, topic, callback):
        self.subscriptions.append((topic, callback))

    async def unsubscribe(self, topic):
        self.unsubscriptions.append(topic)

    def publish_sync(self, **message):
        self.publications.append(message)


class _TopicMapper:
    def get_discovery_control_topic(self):
        return "smarttub/discovery/control"

    def publish_discovery_status(self, state):
        assert state == "running"
        return [
            SimpleNamespace(
                topic="smarttub/discovery/status",
                payload="running",
                qos=1,
                retain=True,
            )
        ]


@pytest.mark.asyncio
async def test_start_publish_and_stop_manage_the_mqtt_boundary():
    coordinator = _Coordinator()
    mqtt_client = _MQTTClient()
    handler = DiscoveryMQTTHandler(coordinator, _TopicMapper(), mqtt_client)

    await handler.start()
    await coordinator.publisher("running")
    await handler.stop()

    assert mqtt_client.subscriptions == [
        ("smarttub/discovery/control", handler._on_control_message)
    ]
    assert coordinator.status_publications == 1
    assert mqtt_client.publications == [
        {
            "topic": "smarttub/discovery/status",
            "payload": "running",
            "qos": 1,
            "retain": True,
        }
    ]
    assert mqtt_client.unsubscriptions == ["smarttub/discovery/control"]


@pytest.mark.asyncio
async def test_valid_control_messages_schedule_start_and_stop():
    coordinator = _Coordinator()
    handler = DiscoveryMQTTHandler(
        coordinator,
        _TopicMapper(),
        _MQTTClient(),
        event_loop=asyncio.get_running_loop(),
    )

    handler._on_control_message("ignored", b'{"action":"start","mode":"full"}')
    handler._on_control_message("ignored", '{"action":"stop"}')
    await asyncio.sleep(0.01)

    assert coordinator.starts == ["full"]
    assert coordinator.stops == 1


@pytest.mark.asyncio
async def test_invalid_or_unschedulable_control_messages_do_nothing():
    coordinator = _Coordinator()
    handler = DiscoveryMQTTHandler(coordinator, _TopicMapper(), _MQTTClient())

    handler._on_control_message("ignored", b"not-json")
    handler._on_control_message("ignored", b'{"action":"restart"}')
    handler._on_control_message("ignored", b'{"action":"start"}')
    handler._on_control_message("ignored", b'{"action":"stop"}')
    await asyncio.sleep(0)

    assert coordinator.starts == []
    assert coordinator.stops == 0
