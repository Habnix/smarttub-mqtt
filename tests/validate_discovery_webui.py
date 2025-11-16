#!/usr/bin/env python3
"""
Validation script for Discovery WebUI Integration.

Tests REST API endpoints.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Direct imports
from fastapi.testclient import TestClient
from src.web.app import create_app
from src.core.discovery_coordinator import DiscoveryCoordinator


def create_mock_config():
    """Create mock config."""
    config = MagicMock()
    config.mqtt = MagicMock()
    config.mqtt.broker = "test-broker"
    config.mqtt.base_topic = "smarttub-mqtt"
    config.web = MagicMock()
    config.web.auth_enabled = False
    config.smarttub = MagicMock()
    config.smarttub.device_id = "test-spa"
    return config


def create_mock_state_manager():
    """Create mock state manager."""
    state_manager = MagicMock()
    state_manager._last_snapshot = {
        "timestamp": "2025-11-09T12:00:00Z",
        "components": {}
    }
    state_manager.get_safe_fallback_state = MagicMock(return_value={})
    return state_manager


def create_mock_smarttub_client():
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


async def test_discovery_status_endpoint():
    """Test GET /api/discovery/status endpoint."""
    print("Testing GET /api/discovery/status...")
    
    config = create_mock_config()
    state_manager = create_mock_state_manager()
    smarttub_client = create_mock_smarttub_client()
    
    # Create coordinator
    coordinator = DiscoveryCoordinator(
        smarttub_client=smarttub_client,
        config=config
    )
    
    # Create app
    app = create_app(
        config=config,
        state_manager=state_manager,
        smarttub_client=smarttub_client,
        discovery_coordinator=coordinator
    )
    
    client = TestClient(app)
    
    # Test endpoint
    response = client.get("/api/discovery/status")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    assert data["success"], "Should return success"
    assert "status" in data, "Should have status field"
    assert data["status"] == "idle", "Should start as idle"
    
    print("✓ Status endpoint works")
    
    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_start_discovery_endpoint():
    """Test POST /api/discovery/start endpoint."""
    print("\nTesting POST /api/discovery/start...")
    
    config = create_mock_config()
    state_manager = create_mock_state_manager()
    smarttub_client = create_mock_smarttub_client()
    
    # Create coordinator
    coordinator = DiscoveryCoordinator(
        smarttub_client=smarttub_client,
        config=config
    )
    
    # Create app
    app = create_app(
        config=config,
        state_manager=state_manager,
        smarttub_client=smarttub_client,
        discovery_coordinator=coordinator
    )
    
    client = TestClient(app)
    
    # Test valid start
    response = client.post("/api/discovery/start", json={"mode": "yaml_only"})
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    assert data["success"], "Should start successfully"
    assert data["mode"] == "yaml_only", "Mode should be yaml_only"
    
    print("✓ Start endpoint works")
    
    # Wait for completion
    await asyncio.sleep(0.5)
    
    # Test invalid mode
    response = client.post("/api/discovery/start", json={"mode": "invalid"})
    assert response.status_code == 400, "Should reject invalid mode"
    
    print("✓ Invalid mode rejected")
    
    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_stop_discovery_endpoint():
    """Test POST /api/discovery/stop endpoint."""
    print("\nTesting POST /api/discovery/stop...")
    
    config = create_mock_config()
    state_manager = create_mock_state_manager()
    smarttub_client = create_mock_smarttub_client()
    
    # Create coordinator
    coordinator = DiscoveryCoordinator(
        smarttub_client=smarttub_client,
        config=config
    )
    
    # Create app
    app = create_app(
        config=config,
        state_manager=state_manager,
        smarttub_client=smarttub_client,
        discovery_coordinator=coordinator
    )
    
    client = TestClient(app)
    
    # Try to stop when nothing running
    response = client.post("/api/discovery/stop")
    assert response.status_code == 400, "Should fail when not running"
    
    print("✓ Stop endpoint works")
    
    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_results_endpoint():
    """Test GET /api/discovery/results endpoint."""
    print("\nTesting GET /api/discovery/results...")
    
    config = create_mock_config()
    state_manager = create_mock_state_manager()
    smarttub_client = create_mock_smarttub_client()
    
    # Create coordinator
    coordinator = DiscoveryCoordinator(
        smarttub_client=smarttub_client,
        config=config
    )
    
    # Create app
    app = create_app(
        config=config,
        state_manager=state_manager,
        smarttub_client=smarttub_client,
        discovery_coordinator=coordinator
    )
    
    client = TestClient(app)
    
    # Try to get results when none available
    response = client.get("/api/discovery/results")
    assert response.status_code == 404, "Should return 404 when no results"
    
    print("✓ Results endpoint works")
    
    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_reset_endpoint():
    """Test POST /api/discovery/reset endpoint."""
    print("\nTesting POST /api/discovery/reset...")
    
    config = create_mock_config()
    state_manager = create_mock_state_manager()
    smarttub_client = create_mock_smarttub_client()
    
    # Create coordinator
    coordinator = DiscoveryCoordinator(
        smarttub_client=smarttub_client,
        config=config
    )
    
    # Create app
    app = create_app(
        config=config,
        state_manager=state_manager,
        smarttub_client=smarttub_client,
        discovery_coordinator=coordinator
    )
    
    client = TestClient(app)
    
    # Reset state
    response = client.post("/api/discovery/reset")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    assert data["success"], "Should reset successfully"
    
    print("✓ Reset endpoint works")
    
    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def test_discovery_page():
    """Test GET /discovery page."""
    print("\nTesting GET /discovery page...")
    
    config = create_mock_config()
    state_manager = create_mock_state_manager()
    smarttub_client = create_mock_smarttub_client()
    
    # Create coordinator
    coordinator = DiscoveryCoordinator(
        smarttub_client=smarttub_client,
        config=config
    )
    
    # Create app
    app = create_app(
        config=config,
        state_manager=state_manager,
        smarttub_client=smarttub_client,
        discovery_coordinator=coordinator
    )
    
    client = TestClient(app)
    
    # Get discovery page
    response = client.get("/discovery")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert "text/html" in response.headers["content-type"], "Should return HTML"
    assert b"Light Mode Discovery" in response.content, "Should contain page title"
    
    print("✓ Discovery page renders")
    
    # Cleanup
    await DiscoveryCoordinator.shutdown()


async def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Discovery WebUI Integration Validation")
    print("=" * 60)
    
    try:
        await test_discovery_status_endpoint()
        await test_start_discovery_endpoint()
        await test_stop_discovery_endpoint()
        await test_results_endpoint()
        await test_reset_endpoint()
        await test_discovery_page()
        
        print("\n" + "=" * 60)
        print("🎉 Discovery WebUI integration validation successful!")
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
