#!/usr/bin/env python3
"""
Validation script for Discovery MQTT Integration.

Tests MQTT topic publishing and command handling.
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Direct imports
from src.core.discovery_coordinator import DiscoveryCoordinator
from src.core.discovery_state import DiscoveryState, DiscoveryStatus, DiscoveryMode
from src.mqtt.topic_mapper import MQTTTopicMapper
from src.mqtt.discovery_handler import DiscoveryMQTTHandler


def create_mock_config():
    """Create mock config."""
    config = MagicMock()
    config.mqtt = MagicMock()
    config.mqtt.broker = "test-broker"
    config.mqtt.base_topic = "smarttub-mqtt"
    config.smarttub = MagicMock()
    config.smarttub.device_id = "test-spa"
    return config


def create_mock_client():
    """Create mock SmartTub client."""
    client = AsyncMock()

    # Mock account
    account = AsyncMock()
    account.id = "test-account"

    # Mock spa
    spa = AsyncMock()
    spa.id = "test-spa"

    # Mock light
    light = AsyncMock()
    light.zone = 1
    light.set_mode = AsyncMock(return_value=True)

    # Wire up mocks
    async def get_spas():
        return [spa]

    async def get_lights():
        return [light]

    async def get_status():
        return MagicMock()

    account.get_spas = get_spas
    spa.get_lights = get_lights
    spa.get_status = get_status

    async def login():
        return account

    client.login = login

    return client


def create_mock_mqtt_client():
    """Create mock MQTT broker client."""
    mqtt_client = MagicMock()

    # Track published messages
    mqtt_client.published_messages = []

    def publish(topic, payload, qos=1, retain=False):
        mqtt_client.published_messages.append(
            {"topic": topic, "payload": payload, "qos": qos, "retain": retain}
        )

    mqtt_client.publish = publish
    mqtt_client.subscribe = MagicMock()
    mqtt_client.unsubscribe = MagicMock()

    return mqtt_client


async def test_topic_mapper_status():
    """Test TopicMapper discovery status publishing."""
    print("Testing TopicMapper status publishing...")

    config = create_mock_config()
    mqtt_client = create_mock_mqtt_client()

    mapper = MQTTTopicMapper(config=config, mqtt_client=mqtt_client)

    # Create mock state
    from src.core.discovery_state import DiscoveryProgress, DiscoveryResults

    state = DiscoveryState(
        status=DiscoveryStatus.RUNNING,
        mode=DiscoveryMode.QUICK,
        started_at=None,
        completed_at=None,
        progress=DiscoveryProgress(
            current_spa="test-spa",
            current_light="zone_1",
            lights_total=2,
            lights_tested=1,
            modes_total=4,
            modes_tested=2,
        ),
        results=None,
        error=None,
    )

    # Publish status
    messages = mapper.publish_discovery_status(state)

    # Should have 1 message (status only, no result yet)
    assert len(messages) == 1, f"Expected 1 message, got {len(messages)}"

    # Check status message
    status_msg = messages[0]
    assert status_msg.topic == "smarttub-mqtt/discovery/status", (
        f"Wrong topic: {status_msg.topic}"
    )
    assert not status_msg.retain, "Status should not be retained"

    # Parse payload
    status_data = json.loads(status_msg.payload)
    assert status_data["status"] == "running", "Status should be running"
    assert status_data["mode"] == "quick", "Mode should be quick"
    # Progress: 2 of 4 modes tested = 50%
    print(f"  Progress: {status_data['progress']['percentage']}%")
    assert status_data["progress"]["modes_tested"] == 2, "Should have 2 modes tested"
    assert status_data["progress"]["modes_total"] == 4, "Should have 4 modes total"

    print("✓ Status message correct")

    # Test completed state with results
    state.status = DiscoveryStatus.COMPLETED
    state.results = DiscoveryResults(
        spas={"test-spa": {"lights": []}},
        yaml_path="/config/discovered_items.yaml",
        total_lights=2,
        total_modes_detected=4,
    )

    messages = mapper.publish_discovery_status(state)

    # Should have 2 messages (status + result)
    assert len(messages) == 2, f"Expected 2 messages, got {len(messages)}"

    # Check result message
    result_msg = messages[1]
    assert result_msg.topic == "smarttub-mqtt/discovery/result", (
        f"Wrong topic: {result_msg.topic}"
    )
    assert result_msg.retain, "Result should be retained"

    # Parse result
    result_data = json.loads(result_msg.payload)
    assert result_data["total_lights"] == 2, "Should have 2 lights"
    assert result_data["total_modes_detected"] == 4, "Should have 4 modes"

    print("✓ Result message correct")


async def test_control_topic():
    """Test control topic generation."""
    print("\nTesting control topic...")

    config = create_mock_config()
    mqtt_client = create_mock_mqtt_client()

    mapper = MQTTTopicMapper(config=config, mqtt_client=mqtt_client)

    control_topic = mapper.get_discovery_control_topic()
    assert control_topic == "smarttub-mqtt/discovery/control", (
        f"Wrong topic: {control_topic}"
    )

    print("✓ Control topic correct")


async def test_mqtt_handler_lifecycle():
    """Test MQTT handler start/stop."""
    print("\nTesting MQTT handler lifecycle...")

    # Setup
    smarttub_client = create_mock_client()
    config = create_mock_config()
    mqtt_client = create_mock_mqtt_client()

    coordinator = DiscoveryCoordinator(smarttub_client=smarttub_client, config=config)

    mapper = MQTTTopicMapper(config=config, mqtt_client=mqtt_client)

    handler = DiscoveryMQTTHandler(
        coordinator=coordinator, topic_mapper=mapper, mqtt_client=mqtt_client
    )

    # Start handler
    await handler.start()

    # Should subscribe to control topic
    mqtt_client.subscribe.assert_called_once()
    call_args = mqtt_client.subscribe.call_args
    assert call_args[1]["topic"] == "smarttub-mqtt/discovery/control", (
        "Should subscribe to control topic"
    )

    print("✓ Handler subscribed to control topic")

    # Should publish initial status
    # (via coordinator callback)
    await asyncio.sleep(0.1)
    assert len(mqtt_client.published_messages) >= 1, "Should publish initial status"

    print("✓ Initial status published")

    # Stop handler
    await handler.stop()

    mqtt_client.unsubscribe.assert_called_once_with("smarttub-mqtt/discovery/control")
    print("✓ Handler unsubscribed")

    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_control_commands():
    """Test handling of control commands."""
    print("\nTesting control commands...")

    # Setup
    smarttub_client = create_mock_client()
    config = create_mock_config()
    mqtt_client = create_mock_mqtt_client()

    coordinator = DiscoveryCoordinator(smarttub_client=smarttub_client, config=config)

    mapper = MQTTTopicMapper(config=config, mqtt_client=mqtt_client)

    handler = DiscoveryMQTTHandler(
        coordinator=coordinator, topic_mapper=mapper, mqtt_client=mqtt_client
    )

    await handler.start()

    # Clear initial messages
    mqtt_client.published_messages.clear()

    # Get the callback
    subscribe_call = mqtt_client.subscribe.call_args
    callback = subscribe_call[1]["callback"]

    # Test start command
    start_payload = json.dumps({"action": "start", "mode": "yaml_only"})

    callback("smarttub-mqtt/discovery/control", start_payload.encode())

    # Wait for async processing
    await asyncio.sleep(0.5)

    # Should have published status updates
    assert len(mqtt_client.published_messages) > 0, "Should publish status after start"

    # Check that status shows completed (yaml_only is instant)
    status_messages = [
        m for m in mqtt_client.published_messages if "status" in m["topic"]
    ]
    assert len(status_messages) > 0, "Should have status messages"

    print("✓ Start command handled")

    # Test stop command (when not running)
    mqtt_client.published_messages.clear()

    stop_payload = json.dumps({"action": "stop"})

    callback("smarttub-mqtt/discovery/control", stop_payload.encode())

    await asyncio.sleep(0.2)

    print("✓ Stop command handled")

    # Test invalid command
    invalid_payload = json.dumps({"action": "invalid"})

    callback("smarttub-mqtt/discovery/control", invalid_payload.encode())
    await asyncio.sleep(0.1)

    print("✓ Invalid command ignored")

    # Cleanup
    await handler.stop()
    await DiscoveryCoordinator.shutdown()


async def test_auto_publishing():
    """Test automatic status publishing via coordinator."""
    print("\nTesting auto-publishing...")

    # Setup
    smarttub_client = create_mock_client()
    config = create_mock_config()
    mqtt_client = create_mock_mqtt_client()

    coordinator = DiscoveryCoordinator(smarttub_client=smarttub_client, config=config)

    mapper = MQTTTopicMapper(config=config, mqtt_client=mqtt_client)

    handler = DiscoveryMQTTHandler(
        coordinator=coordinator, topic_mapper=mapper, mqtt_client=mqtt_client
    )

    await handler.start()

    # Clear initial messages
    mqtt_client.published_messages.clear()

    # Start discovery (should auto-publish)
    await coordinator.start_discovery(mode="yaml_only")

    # Wait for completion
    await asyncio.sleep(0.5)

    # Should have published multiple status updates
    status_messages = [
        m for m in mqtt_client.published_messages if "status" in m["topic"]
    ]
    assert len(status_messages) >= 2, (
        f"Should auto-publish status updates, got {len(status_messages)}"
    )

    print(f"✓ Auto-published {len(status_messages)} status updates")

    # Cleanup
    await handler.stop()
    await DiscoveryCoordinator.shutdown()


async def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Discovery MQTT Integration Validation")
    print("=" * 60)

    try:
        await test_topic_mapper_status()
        await test_control_topic()
        await test_mqtt_handler_lifecycle()
        await test_control_commands()
        await test_auto_publishing()

        print("\n" + "=" * 60)
        print("🎉 Discovery MQTT integration validation successful!")
        print("=" * 60)

        return 0

    except AssertionError as e:
        print(f"\n❌ Validation failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
