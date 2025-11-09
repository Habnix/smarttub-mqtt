"""
Discovery MQTT Handler.

Handles MQTT messages for discovery control and publishes status updates.
"""

import asyncio
import json
import logging
from typing import Optional

from src.core.discovery_coordinator import DiscoveryCoordinator
from src.core.discovery_state import DiscoveryState
from src.mqtt.topic_mapper import MQTTTopicMapper

logger = logging.getLogger(__name__)


class DiscoveryMQTTHandler:
    """
    Handles MQTT integration for discovery operations.
    
    - Subscribes to control topic for start/stop commands
    - Publishes status updates automatically via coordinator
    - Publishes results when discovery completes
    
    Usage:
        handler = DiscoveryMQTTHandler(
            coordinator=coordinator,
            topic_mapper=topic_mapper,
            mqtt_client=mqtt_client
        )
        
        # Start handling
        await handler.start()
        
        # Stop handling
        await handler.stop()
    """
    
    def __init__(
        self,
        coordinator: DiscoveryCoordinator,
        topic_mapper: MQTTTopicMapper,
        mqtt_client: any,
    ):
        """
        Initialize MQTT handler.
        
        Args:
            coordinator: Discovery coordinator instance
            topic_mapper: MQTT topic mapper
            mqtt_client: MQTT broker client
        """
        self.coordinator = coordinator
        self.topic_mapper = topic_mapper
        self.mqtt_client = mqtt_client
        
        self._subscribed = False
        
        logger.info("DiscoveryMQTTHandler initialized")
    
    async def start(self):
        """
        Start MQTT handling.
        
        - Subscribe to control topic
        - Register coordinator callback for auto-publishing
        """
        # Register MQTT publisher with coordinator
        self.coordinator.set_mqtt_publisher(self._publish_status)
        
        # Subscribe to control topic
        control_topic = self.topic_mapper.get_discovery_control_topic()
        self.mqtt_client.subscribe(
            topic=control_topic,
            callback=self._on_control_message
        )
        self._subscribed = True
        
        logger.info(f"Discovery MQTT handler started, subscribed to {control_topic}")
        
        # Publish initial status
        await self.coordinator.publish_status_to_mqtt()
    
    async def stop(self):
        """
        Stop MQTT handling.
        
        - Unsubscribe from control topic
        """
        if self._subscribed:
            control_topic = self.topic_mapper.get_discovery_control_topic()
            self.mqtt_client.unsubscribe(control_topic)
            self._subscribed = False
            
            logger.info("Discovery MQTT handler stopped")
    
    async def _publish_status(self, state: DiscoveryState):
        """
        Publish discovery status to MQTT.
        
        Called automatically by coordinator when state changes.
        
        Args:
            state: Current discovery state
        """
        try:
            messages = self.topic_mapper.publish_discovery_status(state)
            
            # Publish all messages
            for msg in messages:
                self.mqtt_client.publish(
                    topic=msg.topic,
                    payload=msg.payload,
                    qos=msg.qos,
                    retain=msg.retain
                )
            
            logger.debug(f"Published {len(messages)} discovery status messages")
        
        except Exception as e:
            logger.error(f"Failed to publish discovery status: {e}", exc_info=True)
    
    def _on_control_message(self, topic: str, payload: bytes):
        """
        Handle control messages from MQTT.
        
        Expected payload format:
        {
            "action": "start" | "stop",
            "mode": "full" | "quick" | "yaml_only"  (only for start)
        }
        
        Args:
            topic: MQTT topic
            payload: Message payload
        """
        try:
            # Parse JSON payload
            try:
                data = json.loads(payload.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(f"Invalid JSON in discovery control message: {e}")
                return
            
            # Validate action
            action = data.get("action")
            if action not in ["start", "stop"]:
                logger.warning(f"Invalid discovery action: {action}")
                return
            
            # Handle action
            if action == "start":
                mode = data.get("mode", "quick")
                logger.info(f"MQTT control: Starting discovery (mode={mode})")
                
                # Schedule async start
                asyncio.create_task(self._handle_start_command(mode))
            
            elif action == "stop":
                logger.info("MQTT control: Stopping discovery")
                
                # Schedule async stop
                asyncio.create_task(self._handle_stop_command())
        
        except Exception as e:
            logger.error(f"Error handling discovery control message: {e}", exc_info=True)
    
    async def _handle_start_command(self, mode: str):
        """
        Handle start command asynchronously.
        
        Args:
            mode: Discovery mode
        """
        try:
            result = await self.coordinator.start_discovery(mode=mode)
            
            if result["success"]:
                logger.info(f"Discovery started via MQTT: mode={mode}")
            else:
                logger.warning(f"Failed to start discovery via MQTT: {result.get('error')}")
        
        except Exception as e:
            logger.error(f"Error starting discovery via MQTT: {e}", exc_info=True)
    
    async def _handle_stop_command(self):
        """
        Handle stop command asynchronously.
        """
        try:
            result = await self.coordinator.stop_discovery()
            
            if result["success"]:
                logger.info("Discovery stopped via MQTT")
            else:
                logger.warning(f"Failed to stop discovery via MQTT: {result.get('error')}")
        
        except Exception as e:
            logger.error(f"Error stopping discovery via MQTT: {e}", exc_info=True)
