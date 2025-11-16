#!/usr/bin/env python3
"""
Validation script for Background Discovery Runner.
Tests with mocked SmartTub client.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Direct import
import importlib.util

# Load discovery_state
spec_state = importlib.util.spec_from_file_location(
    "discovery_state",
    Path(__file__).parent.parent / "src" / "core" / "discovery_state.py",
)
discovery_state = importlib.util.module_from_spec(spec_state)
spec_state.loader.exec_module(discovery_state)

# Load background_discovery
spec_runner = importlib.util.spec_from_file_location(
    "background_discovery",
    Path(__file__).parent.parent / "src" / "core" / "background_discovery.py",
)
background_discovery = importlib.util.module_from_spec(spec_runner)

# Mock dependencies before loading
sys.modules["src.core.discovery_state"] = discovery_state
sys.modules["src.core.smarttub_client"] = MagicMock()
sys.modules["src.core.config_loader"] = MagicMock()
sys.modules["smarttub"] = MagicMock()

spec_runner.loader.exec_module(background_discovery)

DiscoveryStateManager = discovery_state.DiscoveryStateManager
DiscoveryStatus = discovery_state.DiscoveryStatus
DiscoveryMode = discovery_state.DiscoveryMode
BackgroundDiscoveryRunner = background_discovery.BackgroundDiscoveryRunner


def create_mock_light(zone: int):
    """Create a mock light object."""
    light = AsyncMock()
    light.zone = zone
    light.set_mode = AsyncMock()
    return light


def create_mock_spa(spa_id: str, num_lights: int = 2):
    """Create a mock spa object."""
    spa = AsyncMock()
    spa.id = spa_id

    # Mock get_status
    spa.get_status = AsyncMock(return_value=Mock())

    # Mock get_lights
    lights = [create_mock_light(i + 1) for i in range(num_lights)]
    spa.get_lights = AsyncMock(return_value=lights)

    return spa


def create_mock_account(spas: list):
    """Create a mock account object."""
    account = AsyncMock()
    account.get_spas = AsyncMock(return_value=spas)
    return account


def create_mock_client(num_spas: int = 1, lights_per_spa: int = 2):
    """Create a mock SmartTub client."""
    client = AsyncMock()

    # Create spas
    spas = [create_mock_spa(f"spa_{i}", lights_per_spa) for i in range(num_spas)]

    # Create account
    account = create_mock_account(spas)
    client.get_account = AsyncMock(return_value=account)

    return client


async def test_basic_lifecycle():
    """Test basic start/stop lifecycle."""
    print("Testing basic lifecycle...")

    # Create components
    state_manager = DiscoveryStateManager()
    mock_client = create_mock_client()
    mock_config = Mock()

    runner = BackgroundDiscoveryRunner(
        state_manager=state_manager,
        smarttub_client=mock_client,
        config=mock_config,
    )

    # Check initial state
    assert not runner.is_running(), "Should not be running initially"
    print("✓ Initial state: not running")

    # Start discovery (YAML_ONLY mode for speed)
    result = await runner.start_discovery(DiscoveryMode.YAML_ONLY)
    assert result["success"], "Start should succeed"
    assert runner.is_running(), "Should be running after start"
    print("✓ Start discovery succeeded")

    # Wait a bit
    await asyncio.sleep(0.5)

    # Check state
    state = await state_manager.get_state()
    print(f"✓ Status: {state.status.value}")

    # Wait for completion (YAML_ONLY is fast)
    for _ in range(10):
        await asyncio.sleep(0.5)
        if not runner.is_running():
            break

    # Should be completed
    state = await state_manager.get_state()
    print(f"✓ Final status: {state.status.value}")

    # Cannot start while running
    if runner.is_running():
        result2 = await runner.start_discovery(DiscoveryMode.YAML_ONLY)
        assert not result2["success"], "Should fail to start while running"
        print("✓ Cannot start while running")


async def test_stop_discovery():
    """Test stopping discovery."""
    print("\nTesting stop discovery...")

    # Create components
    state_manager = DiscoveryStateManager()
    mock_client = create_mock_client()
    mock_config = Mock()

    runner = BackgroundDiscoveryRunner(
        state_manager=state_manager,
        smarttub_client=mock_client,
        config=mock_config,
    )

    # Start discovery
    await runner.start_discovery(DiscoveryMode.QUICK)
    await asyncio.sleep(0.2)

    # Stop discovery
    result = await runner.stop_discovery()
    assert result["success"], "Stop should succeed"
    print("✓ Stop discovery succeeded")

    # Should not be running
    await asyncio.sleep(0.5)
    assert not runner.is_running(), "Should not be running after stop"
    print("✓ Discovery stopped")

    # State should reflect stop
    state = await state_manager.get_state()
    assert state.status in [DiscoveryStatus.IDLE, DiscoveryStatus.COMPLETED]
    print(f"✓ State after stop: {state.status.value}")


async def test_progress_updates():
    """Test progress updates during discovery."""
    print("\nTesting progress updates...")

    # Create components
    state_manager = DiscoveryStateManager()
    mock_client = create_mock_client(num_spas=1, lights_per_spa=2)
    mock_config = Mock()

    runner = BackgroundDiscoveryRunner(
        state_manager=state_manager,
        smarttub_client=mock_client,
        config=mock_config,
    )

    # Track progress updates
    progress_updates = []

    async def track_progress(state):
        if state.status == DiscoveryStatus.RUNNING:
            progress_updates.append(state.progress.percentage)

    state_manager.subscribe(track_progress)

    # Start discovery
    await runner.start_discovery(DiscoveryMode.YAML_ONLY)

    # Wait for completion
    for _ in range(20):
        await asyncio.sleep(0.5)
        if not runner.is_running():
            break

    # Should have received progress updates
    print(f"✓ Received {len(progress_updates)} progress updates")
    if progress_updates:
        print(
            f"✓ Progress range: {min(progress_updates):.1f}% - {max(progress_updates):.1f}%"
        )


async def test_mode_configurations():
    """Test different discovery modes."""
    print("\nTesting mode configurations...")

    state_manager = DiscoveryStateManager()
    mock_client = create_mock_client()
    mock_config = Mock()

    runner = BackgroundDiscoveryRunner(
        state_manager=state_manager,
        smarttub_client=mock_client,
        config=mock_config,
    )

    # Check mode configs exist
    assert DiscoveryMode.FULL in runner.mode_configs
    assert DiscoveryMode.QUICK in runner.mode_configs
    assert DiscoveryMode.YAML_ONLY in runner.mode_configs
    print("✓ All mode configurations present")

    # Check QUICK mode config
    quick_config = runner.mode_configs[DiscoveryMode.QUICK]
    assert quick_config["test_modes"] is True
    assert len(quick_config["modes_to_test"]) == 4  # OFF, ON, PURPLE, WHITE
    print(f"✓ QUICK mode: {len(quick_config['modes_to_test'])} modes")

    # Check YAML_ONLY mode
    yaml_config = runner.mode_configs[DiscoveryMode.YAML_ONLY]
    assert yaml_config["test_modes"] is False
    print("✓ YAML_ONLY mode: no testing")


async def main():
    """Run all tests."""
    try:
        await test_basic_lifecycle()
        await test_stop_discovery()
        await test_progress_updates()
        await test_mode_configurations()

        print("\n🎉 Background Discovery Runner validation successful!")
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
