#!/usr/bin/env python3
"""
Simple validation script for Discovery Coordinator.

Uses direct imports (requires all dependencies).
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from typing import List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Direct imports
from src.core.discovery_coordinator import DiscoveryCoordinator
from src.core.discovery_state import DiscoveryState, DiscoveryStatus


def create_mock_config():
    """Create mock config."""
    config = MagicMock()
    config.mqtt = MagicMock()
    config.mqtt.broker = "test-broker"
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


async def test_singleton_pattern():
    """Test that coordinator is a singleton."""
    print("Testing singleton pattern...")

    client1 = create_mock_client()
    config1 = create_mock_config()

    # Create first instance
    coordinator1 = DiscoveryCoordinator(smarttub_client=client1, config=config1)

    # Create "second" instance
    client2 = create_mock_client()
    config2 = create_mock_config()

    coordinator2 = DiscoveryCoordinator(smarttub_client=client2, config=config2)

    # Should be same instance
    assert coordinator1 is coordinator2, "Coordinator should be singleton"
    print("✓ Singleton pattern working")

    # Cleanup for next tests
    await DiscoveryCoordinator.shutdown()


async def test_basic_lifecycle():
    """Test start/stop lifecycle via coordinator."""
    print("\nTesting basic lifecycle...")

    client = create_mock_client()
    config = create_mock_config()

    coordinator = DiscoveryCoordinator(smarttub_client=client, config=config)

    # Get initial status
    status = await coordinator.get_status()
    assert status["success"], "Should get status"
    assert status["status"] == "idle", "Should start as idle"
    assert not coordinator.is_running(), "Should not be running"
    print("✓ Initial state correct")

    # Start discovery (YAML_ONLY for quick test)
    result = await coordinator.start_discovery(mode="yaml_only")
    assert result["success"], f"Should start discovery: {result.get('error')}"
    print("✓ Discovery started")

    # Wait a moment for completion
    await asyncio.sleep(0.5)

    # Check final status
    status = await coordinator.get_status()
    assert status["success"], "Should get status"
    print(f"✓ Final status: {status['status']}")

    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_invalid_mode():
    """Test handling of invalid mode."""
    print("\nTesting invalid mode handling...")

    client = create_mock_client()
    config = create_mock_config()

    coordinator = DiscoveryCoordinator(smarttub_client=client, config=config)

    # Try invalid mode
    result = await coordinator.start_discovery(mode="invalid_mode")
    assert not result["success"], "Should reject invalid mode"
    assert "Invalid mode" in result["error"], "Should have error message"
    print("✓ Invalid mode rejected")

    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_concurrent_start():
    """Test that only one discovery can run at a time."""
    print("\nTesting concurrent start protection...")

    client = create_mock_client()
    config = create_mock_config()

    coordinator = DiscoveryCoordinator(smarttub_client=client, config=config)

    # Start first discovery
    result1 = await coordinator.start_discovery(mode="yaml_only")
    assert result1["success"], "First start should succeed"

    # Try to start second discovery immediately
    result2 = await coordinator.start_discovery(mode="yaml_only")
    assert not result2["success"], "Second start should fail"
    assert "already running" in result2["error"].lower(), (
        "Should indicate already running"
    )
    print("✓ Concurrent start prevented")

    # Wait for completion
    await asyncio.sleep(0.5)

    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_mqtt_publisher():
    """Test MQTT publisher registration and callbacks."""
    print("\nTesting MQTT publisher...")

    client = create_mock_client()
    config = create_mock_config()

    coordinator = DiscoveryCoordinator(smarttub_client=client, config=config)

    # Track published states
    published_states: List[DiscoveryState] = []

    async def mock_publisher(state: DiscoveryState):
        """Mock MQTT publisher."""
        published_states.append(state)

    # Register publisher
    coordinator.set_mqtt_publisher(mock_publisher)
    print("✓ Publisher registered")

    # Start discovery (should trigger publications)
    await coordinator.start_discovery(mode="yaml_only")

    # Wait for completion and publications
    await asyncio.sleep(0.5)

    # Should have received at least 2 publications (running, completed)
    assert len(published_states) >= 2, (
        f"Should publish states, got {len(published_states)}"
    )
    print(f"✓ Received {len(published_states)} state publications")

    # Check status values
    statuses = [s.status for s in published_states]
    assert DiscoveryStatus.RUNNING in statuses, "Should publish RUNNING state"
    print("✓ RUNNING state published")

    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_manual_mqtt_publish():
    """Test manual MQTT publishing."""
    print("\nTesting manual MQTT publish...")

    client = create_mock_client()
    config = create_mock_config()

    coordinator = DiscoveryCoordinator(smarttub_client=client, config=config)

    # Track publications
    publish_count = [0]

    async def mock_publisher(state: DiscoveryState):
        publish_count[0] += 1

    coordinator.set_mqtt_publisher(mock_publisher)

    # Manually trigger publish
    await coordinator.publish_status_to_mqtt()

    assert publish_count[0] >= 1, "Should publish at least once"
    print(f"✓ Manual publish triggered ({publish_count[0]} calls)")

    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_stop_discovery():
    """Test stopping discovery."""
    print("\nTesting stop discovery...")

    client = create_mock_client()
    config = create_mock_config()

    coordinator = DiscoveryCoordinator(smarttub_client=client, config=config)

    # Try to stop when nothing is running
    result = await coordinator.stop_discovery()
    assert not result["success"], "Should fail to stop when not running"
    print("✓ Cannot stop when not running")

    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_reset_state():
    """Test state reset."""
    print("\nTesting state reset...")

    client = create_mock_client()
    config = create_mock_config()

    coordinator = DiscoveryCoordinator(smarttub_client=client, config=config)

    # Start and complete discovery
    await coordinator.start_discovery(mode="yaml_only")
    await asyncio.sleep(0.5)

    # Reset state
    result = await coordinator.reset_state()
    assert result["success"], f"Should reset state: {result.get('error')}"
    print("✓ State reset")

    # Check state is idle
    status = await coordinator.get_status()
    assert status["status"] == "idle", "Should be idle after reset"
    print("✓ State is idle after reset")

    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_get_instance():
    """Test get_instance class method."""
    print("\nTesting get_instance...")

    # Should be None initially
    instance = DiscoveryCoordinator.get_instance()
    assert instance is None, "Should be None before creation"

    # Create instance
    client = create_mock_client()
    config = create_mock_config()
    coordinator = DiscoveryCoordinator(smarttub_client=client, config=config)

    # Now should return instance
    instance = DiscoveryCoordinator.get_instance()
    assert instance is coordinator, "Should return same instance"
    print("✓ get_instance() working")

    # Cleanup
    await DiscoveryCoordinator.shutdown()

    # Should be None after shutdown
    instance = DiscoveryCoordinator.get_instance()
    assert instance is None, "Should be None after shutdown"
    print("✓ Instance cleared after shutdown")


async def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Discovery Coordinator Validation")
    print("=" * 60)

    try:
        await test_singleton_pattern()
        await test_basic_lifecycle()
        await test_invalid_mode()
        await test_concurrent_start()
        await test_mqtt_publisher()
        await test_manual_mqtt_publish()
        await test_stop_discovery()
        await test_reset_state()
        await test_get_instance()

        print("\n" + "=" * 60)
        print("🎉 Discovery Coordinator validation successful!")
        print("=" * 60)

        return 0

    except AssertionError as e:
        print(f"\n❌ Validation failed: {e}")
        return 1

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
