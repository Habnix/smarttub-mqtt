#!/usr/bin/env python3
"""
Quick validation script for Discovery State Manager.
Runs basic checks without pytest.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Direct import of the module file
import importlib.util

spec = importlib.util.spec_from_file_location(
    "discovery_state",
    Path(__file__).parent.parent / "src" / "core" / "discovery_state.py",
)
discovery_state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery_state)

DiscoveryState = discovery_state.DiscoveryState
DiscoveryStatus = discovery_state.DiscoveryStatus
DiscoveryMode = discovery_state.DiscoveryMode
DiscoveryProgress = discovery_state.DiscoveryProgress
DiscoveryStateManager = discovery_state.DiscoveryStateManager


async def test_basic_functionality():
    """Test basic state manager functionality."""
    print("Testing Discovery State Manager...")

    # Create manager
    manager = DiscoveryStateManager()
    print("✓ Manager created")

    # Test initial state
    state = await manager.get_state()
    assert state.status == DiscoveryStatus.IDLE, "Initial status should be IDLE"
    print("✓ Initial state is IDLE")

    # Test status update
    await manager.update_state({"status": DiscoveryStatus.RUNNING})
    state = await manager.get_state()
    assert state.status == DiscoveryStatus.RUNNING, "Status should be RUNNING"
    print("✓ Status update works")

    # Test mode update
    await manager.update_state({"mode": DiscoveryMode.QUICK})
    state = await manager.get_state()
    assert state.mode == DiscoveryMode.QUICK, "Mode should be QUICK"
    print("✓ Mode update works")

    # Test progress update
    await manager.update_progress(
        current_spa="100946961",
        lights_total=2,
        lights_tested=1,
        modes_total=36,
        modes_tested=18,
    )
    state = await manager.get_state()
    assert state.progress.percentage == 50.0, "Progress should be 50%"
    print("✓ Progress update works (50.0%)")

    # Test observer
    notifications = []

    async def observer(state):
        notifications.append(state.status)

    manager.subscribe(observer)
    await manager.update_state({"status": DiscoveryStatus.COMPLETED})
    await asyncio.sleep(0.1)  # Give time for notification

    assert len(notifications) == 1, "Should receive 1 notification"
    assert notifications[0] == DiscoveryStatus.COMPLETED
    print("✓ Observer notifications work")

    # Test reset
    await manager.reset()
    state = await manager.get_state()
    assert state.status == DiscoveryStatus.IDLE, "Status should be IDLE after reset"
    assert state.mode is None, "Mode should be None after reset"
    print("✓ Reset works")

    # Test to_dict
    data = state.to_dict()
    assert isinstance(data, dict), "to_dict should return dict"
    assert data["status"] == "idle"
    print("✓ Serialization works")

    print("\n✅ All tests passed!")


async def test_concurrent_updates():
    """Test thread-safety with concurrent updates."""
    print("\nTesting concurrent updates...")

    manager = DiscoveryStateManager()

    async def update_progress(n: int):
        await manager.update_progress(modes_tested=n)

    # Run 100 concurrent updates
    await asyncio.gather(*[update_progress(i) for i in range(100)])

    state = await manager.get_state()
    print(
        f"✓ Concurrent updates completed (final value: {state.progress.modes_tested})"
    )


async def main():
    """Run all tests."""
    try:
        await test_basic_functionality()
        await test_concurrent_updates()
        print("\n🎉 Discovery State Manager validation successful!")
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
