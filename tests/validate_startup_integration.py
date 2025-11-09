#!/usr/bin/env python3
"""
Validation script for Startup Integration.

Tests YAML Fallback Publisher.
"""

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import yaml

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Direct imports
from src.core.yaml_fallback import YAMLFallbackPublisher
from src.mqtt.topic_mapper import MQTTTopicMapper


def create_mock_config():
    """Create mock config."""
    config = MagicMock()
    config.mqtt = MagicMock()
    config.mqtt.base_topic = "smarttub-mqtt"
    return config


def create_mock_mqtt_client():
    """Create mock MQTT client."""
    mqtt_client = MagicMock()
    mqtt_client.published_messages = []
    
    def publish(topic, payload, qos=1, retain=False):
        mqtt_client.published_messages.append({
            "topic": topic,
            "payload": payload,
            "qos": qos,
            "retain": retain
        })
    
    mqtt_client.publish = publish
    return mqtt_client


def create_test_yaml(path: Path):
    """Create test discovered_items.yaml."""
    data = {
        "discovered_items": {
            "test-spa-1": {
                "lights": [
                    {
                        "id": "zone_1",
                        "detected_modes": ["OFF", "ON", "PURPLE", "WHITE"]
                    },
                    {
                        "id": "zone_2",
                        "detected_modes": ["OFF", "ON"]
                    }
                ]
            },
            "test-spa-2": {
                "lights": [
                    {
                        "id": "zone_1",
                        "detected_modes": ["OFF", "HIGH_SPEED_COLOR_WHEEL"]
                    }
                ]
            }
        }
    }
    
    with open(path, 'w') as f:
        yaml.dump(data, f)


async def test_yaml_fallback_publishing():
    """Test YAML fallback publishing."""
    print("Testing YAML fallback publishing...")
    
    # Create temporary YAML file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        temp_path = Path(f.name)
    
    try:
        # Create test YAML
        create_test_yaml(temp_path)
        
        # Setup mocks
        config = create_mock_config()
        mqtt_client = create_mock_mqtt_client()
        
        topic_mapper = MQTTTopicMapper(config=config, mqtt_client=mqtt_client)
        
        # Create publisher
        publisher = YAMLFallbackPublisher(topic_mapper=topic_mapper)
        
        # Publish from YAML
        result = await publisher.publish_from_yaml(yaml_path=temp_path)
        
        assert result == True, "Should publish successfully"
        print("✓ Publishing returned success")
        
        # Check published messages
        messages = mqtt_client.published_messages
        
        # Should have 3 lights total (2 from spa-1, 1 from spa-2)
        assert len(messages) == 3, f"Expected 3 messages, got {len(messages)}"
        print(f"✓ Published {len(messages)} light metadata messages")
        
        # Check topics
        topics = [m["topic"] for m in messages]
        expected_topics = [
            "smarttub-mqtt/test-spa-1/light/zone_1/meta/detected_modes",
            "smarttub-mqtt/test-spa-1/light/zone_2/meta/detected_modes",
            "smarttub-mqtt/test-spa-2/light/zone_1/meta/detected_modes",
        ]
        
        for expected in expected_topics:
            assert expected in topics, f"Missing topic: {expected}"
        
        print("✓ All expected topics published")
        
        # Check payloads
        zone_1_msg = next(m for m in messages if "zone_1" in m["topic"] and "spa-1" in m["topic"])
        assert zone_1_msg["payload"] == "OFF,ON,PURPLE,WHITE", f"Wrong payload: {zone_1_msg['payload']}"
        
        zone_2_msg = next(m for m in messages if "zone_2" in m["topic"])
        assert zone_2_msg["payload"] == "OFF,ON", f"Wrong payload: {zone_2_msg['payload']}"
        
        print("✓ Payloads correct")
        
        # Check retain flag
        for msg in messages:
            assert msg["retain"] == True, "Messages should be retained"
        
        print("✓ Messages retained")
    
    finally:
        # Cleanup
        temp_path.unlink()


async def test_yaml_not_found():
    """Test handling of missing YAML file."""
    print("\nTesting missing YAML file...")
    
    config = create_mock_config()
    mqtt_client = create_mock_mqtt_client()
    
    topic_mapper = MQTTTopicMapper(config=config, mqtt_client=mqtt_client)
    publisher = YAMLFallbackPublisher(topic_mapper=topic_mapper)
    
    # Try to publish from non-existent file
    result = await publisher.publish_from_yaml(yaml_path=Path("/nonexistent/file.yaml"))
    
    assert result == False, "Should return False for missing file"
    print("✓ Returns False for missing file")
    
    # Should not publish anything
    assert len(mqtt_client.published_messages) == 0, "Should not publish anything"
    print("✓ No messages published")


async def test_invalid_yaml():
    """Test handling of invalid YAML structure."""
    print("\nTesting invalid YAML structure...")
    
    # Create invalid YAML
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        temp_path = Path(f.name)
        f.write("invalid: yaml\nwithout: discovered_items")
    
    try:
        config = create_mock_config()
        mqtt_client = create_mock_mqtt_client()
        
        topic_mapper = MQTTTopicMapper(config=config, mqtt_client=mqtt_client)
        publisher = YAMLFallbackPublisher(topic_mapper=topic_mapper)
        
        # Try to publish from invalid YAML
        result = await publisher.publish_from_yaml(yaml_path=temp_path)
        
        assert result == False, "Should return False for invalid YAML"
        print("✓ Returns False for invalid YAML structure")
        
        # Should not publish anything
        assert len(mqtt_client.published_messages) == 0, "Should not publish anything"
        print("✓ No messages published")
    
    finally:
        temp_path.unlink()


async def test_empty_detected_modes():
    """Test handling of lights without detected_modes."""
    print("\nTesting empty detected_modes...")
    
    # Create YAML with empty detected_modes
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        temp_path = Path(f.name)
    
    try:
        data = {
            "discovered_items": {
                "test-spa": {
                    "lights": [
                        {
                            "id": "zone_1",
                            "detected_modes": []
                        }
                    ]
                }
            }
        }
        
        with open(temp_path, 'w') as f:
            yaml.dump(data, f)
        
        config = create_mock_config()
        mqtt_client = create_mock_mqtt_client()
        
        topic_mapper = MQTTTopicMapper(config=config, mqtt_client=mqtt_client)
        publisher = YAMLFallbackPublisher(topic_mapper=topic_mapper)
        
        # Publish
        result = await publisher.publish_from_yaml(yaml_path=temp_path)
        
        assert result == True, "Should still publish"
        print("✓ Publishing succeeds with empty modes")
        
        # Should publish empty payload
        assert len(mqtt_client.published_messages) == 1, "Should publish 1 message"
        msg = mqtt_client.published_messages[0]
        assert msg["payload"] == "", f"Expected empty payload, got: {msg['payload']}"
        
        print("✓ Empty payload published")
    
    finally:
        temp_path.unlink()


async def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Startup Integration Validation")
    print("=" * 60)
    
    try:
        await test_yaml_fallback_publishing()
        await test_yaml_not_found()
        await test_invalid_yaml()
        await test_empty_detected_modes()
        
        print("\n" + "=" * 60)
        print("🎉 Startup integration validation successful!")
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
