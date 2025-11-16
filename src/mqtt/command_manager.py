from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable
import queue

from src.core.config_loader import AppConfig
from src.core.smarttub_client import SmartTubClient


logger = logging.getLogger("smarttub.mqtt.commands")


class CommandManager:
    """Manages MQTT command subscriptions and execution."""

    def __init__(self, config: AppConfig, smarttub_client: SmartTubClient, mqtt_client: Any):
        self.config = config
        self.smarttub_client = smarttub_client
        self.mqtt_client = mqtt_client
        self._command_handlers: dict[str, Callable] = {}
        self._command_queue: queue.Queue = queue.Queue()
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._state_manager = None  # Will be set after initialization

        self._setup_command_handlers()

    def _setup_command_handlers(self) -> None:
        """Set up command handlers for different components.
        
        According to the write topic convention (T052), writable values follow
        the pattern <value>_writetopic instead of set_<value>, so:
        - target_temperature_writetopic instead of heater/set_temperature
        - mode_writetopic instead of heater/set_mode
        - state_writetopic instead of pumps/set_state etc.
        """
        base_topic = self.config.mqtt.base_topic
        # Register handlers by command path (spa-specific subscription will
        # be applied in `subscribe_commands`). This keeps handlers independent
        # of the spa id and allows subscribing with a wildcard (+/) to catch
        # commands for any spa.
        
        # Heater commands - using _writetopic convention
        self._command_handlers["heater/target_temperature_writetopic"] = self._handle_set_temperature
        self._command_handlers["heater/mode_writetopic"] = self._handle_set_heat_mode

        # Pump commands - using _writetopic convention
        self._command_handlers["pumps/state_writetopic"] = self._handle_set_pump_state

        # Light commands - using _writetopic convention
        self._command_handlers["lights/state_writetopic"] = self._handle_set_light_state
        self._command_handlers["lights/mode_writetopic"] = self._handle_set_light_mode
        self._command_handlers["lights/color_writetopic"] = self._handle_set_light_color
        self._command_handlers["lights/brightness_writetopic"] = self._handle_set_light_brightness

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the event loop for executing async handlers.
        
        This must be called before subscribing to commands to ensure
        handlers can be executed in the correct event loop.
        """
        self._event_loop = loop
        logger.debug(f"Event loop set for CommandManager: {loop}")

    def set_state_manager(self, state_manager) -> None:
        """Set the state manager for triggering immediate state updates after commands.
        
        Args:
            state_manager: StateManager instance
        """
        self._state_manager = state_manager
        logger.debug("State manager set for CommandManager")

    async def process_command_queue(self) -> None:
        """Process commands from the queue in the main event loop.
        
        This should be run as a background task in the main event loop.
        """
        while True:
            try:
                # Check queue without blocking
                try:
                    handler, data = self._command_queue.get_nowait()
                    # Execute the async handler
                    asyncio.create_task(handler(data))
                except queue.Empty:
                    # No commands, wait a bit before checking again
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error processing command queue: {e}", exc_info=True)
                await asyncio.sleep(1)

    def subscribe_commands(self) -> None:
        """Subscribe to all command topics.
        
        Following T052 convention, we subscribe to _writetopic patterns for all
        writable values. Per-component write topics are also supported (e.g.,
        per-pump state_writetopic).
        """
        base_topic = self.config.mqtt.base_topic

        # Subscribe to spa-scoped command topics using a single-level wildcard
        # for the spa id: <base_topic>/+/component/<value>_writetopic
        for command_path in self._command_handlers.keys():
            topic = f"{base_topic}/+/{command_path}"
            self.mqtt_client.subscribe(topic, self._handle_command_message)
            logger.info(f"Subscribed to command topic: {topic}")
        
        # Also subscribe to per-pump command topics under: 
        # <base_topic>/{spa_id}/pumps/{pump_id}/state_writetopic
        # We use single-level wildcards for spa_id and pump_id so handlers can extract them.
        pump_topic = f"{base_topic}/+/pumps/+/state_writetopic"
        self.mqtt_client.subscribe(pump_topic, self._handle_command_message)
        logger.info(f"Subscribed to per-pump command topic: {pump_topic}")
        
        # Also subscribe to per-light command topics:
        # <base_topic>/{spa_id}/lights/{light_id}/state_writetopic
        # <base_topic>/{spa_id}/lights/{light_id}/mode_writetopic
        # <base_topic>/{spa_id}/lights/{light_id}/color_writetopic
        # <base_topic>/{spa_id}/lights/{light_id}/brightness_writetopic
        light_state_topic = f"{base_topic}/+/lights/+/state_writetopic"
        self.mqtt_client.subscribe(light_state_topic, self._handle_command_message)
        logger.info(f"Subscribed to per-light state command topic: {light_state_topic}")
        
        light_mode_topic = f"{base_topic}/+/lights/+/mode_writetopic"
        self.mqtt_client.subscribe(light_mode_topic, self._handle_command_message)
        logger.info(f"Subscribed to per-light mode command topic: {light_mode_topic}")
        
        light_color_topic = f"{base_topic}/+/lights/+/color_writetopic"
        self.mqtt_client.subscribe(light_color_topic, self._handle_command_message)
        logger.info(f"Subscribed to per-light color command topic: {light_color_topic}")
        
        light_brightness_topic = f"{base_topic}/+/lights/+/brightness_writetopic"
        self.mqtt_client.subscribe(light_brightness_topic, self._handle_command_message)
        logger.info(f"Subscribed to per-light brightness command topic: {light_brightness_topic}")

    def _handle_command_message(self, topic: str, payload: str) -> None:
        """Handle incoming command messages.
        
        Supports both the new _writetopic convention and per-component topics
        like pumps/{id}/state_writetopic or lights/{id}/brightness_writetopic.
        """
        logger.info(f"MQTT command received: topic='{topic}', payload='{payload}'")
        try:
            if not self.smarttub_client.spas:
                logger.warning(f"Spa not initialized yet, ignoring command: {topic}, spas: {self.smarttub_client.spas}")
                return
        except AttributeError:
            logger.warning(f"Spa not available yet, ignoring command: {topic}")
            return
        try:
            # Extract the command path relative to base_topic. Expected topic
            # shape: <base_topic>/<spa_id>/<command_path>
            base_topic = self.config.mqtt.base_topic
            if topic.startswith(f"{base_topic}/"):
                remainder = topic[len(f"{base_topic}/"):]
            else:
                remainder = topic

            # remainder should be like '<spa_id>/heater/target_temperature_writetopic'
            parts = remainder.split('/', 1)
            if len(parts) == 2:
                spa_id, command_path = parts[0], parts[1]
            else:
                spa_id = None
                command_path = remainder

            # Support per-pump topics like: 'pumps/<pump_id>/state_writetopic'. 
            # Map to the logical handler key 'pumps/state_writetopic' and inject 
            # 'pump_id' into the parsed data.
            handler = self._command_handlers.get(command_path)
            
            # Detect pumps/<pid>/state_writetopic pattern
            if handler is None and command_path.startswith("pumps/"):
                parts_cmd = command_path.split('/', 2)
                # parts_cmd -> ['pumps', '<pid>', 'state_writetopic'] expected
                if len(parts_cmd) == 3 and parts_cmd[2] == 'state_writetopic':
                    pump_id = parts_cmd[1]
                    # canonical handler key for pump state
                    handler = self._command_handlers.get('pumps/state_writetopic')
                    # Parse payload and inject pump_id
                    raw_data = self._parse_payload(payload)
                    data = self._normalize_command_data(raw_data, pump_id=pump_id)

                    logger.info(f"Executing mapped pump command: pumps/state_writetopic (spa_id={spa_id}) pump_id={pump_id} with payload: {data}")
                    if handler:
                        self._execute_handler(handler, data)
                        return
            
            # Detect lights/<light_id>/<value>_writetopic pattern
            if handler is None and command_path.startswith("lights/"):
                parts_cmd = command_path.split('/', 2)
                # parts_cmd -> ['lights', '<light_id>', 'state_writetopic'] expected
                if len(parts_cmd) == 3 and parts_cmd[2].endswith('_writetopic'):
                    light_id = parts_cmd[1]
                    value_type = parts_cmd[2]  # e.g., state_writetopic, color_writetopic, brightness_writetopic
                    # canonical handler key for light commands
                    handler = self._command_handlers.get(f'lights/{value_type}')
                    # Parse payload and inject light_id
                    raw_data = self._parse_payload(payload)
                    data = self._normalize_command_data(raw_data, light_id=light_id)

                    logger.info(f"Executing mapped light command: lights/{value_type} (spa_id={spa_id}) light_id={light_id} with payload: {data}")
                    if handler:
                        self._execute_handler(handler, data)
                        return
                        
            if handler:
                # Parse JSON payload if possible, otherwise use raw payload
                data = self._parse_payload(payload)

                logger.info(f"Executing command: {command_path} (spa_id={spa_id}) with payload: {data}")
                self._execute_handler(handler, data)
            else:
                logger.warning(f"No handler found for command topic: {topic}")
        except Exception as e:
            logger.error(f"Error handling command {topic}: {e}", exc_info=True)
    
    def _parse_payload(self, payload: str) -> Any:
        """Parse payload as JSON if possible, otherwise return raw string."""
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload
        except Exception:
            return payload
    
    def _normalize_command_data(self, raw_data: Any, pump_id: str = None, light_id: str = None) -> dict:
        """Normalize command data into a consistent dict format.
        
        Args:
            raw_data: Parsed payload (dict, str, int, etc.)
            pump_id: Optional pump ID to inject
            light_id: Optional light ID to inject
            
        Returns:
            Normalized dict with injected IDs
        """
        if isinstance(raw_data, dict):
            data = raw_data.copy()
            if pump_id:
                data['pump_id'] = pump_id
            if light_id:
                data['light_id'] = light_id
            return data
        else:
            # treat scalar payload as the desired state/value string
            value_str = str(raw_data).strip()
            data = {}
            
            # Auto-detect the value type based on content
            if value_str.lower() in ('on', 'off'):
                data['state'] = value_str.lower()
            elif value_str.isdigit():
                # Could be temperature, brightness, etc.
                data['value'] = int(value_str)
            else:
                # Fallback: preserve raw value
                data['value'] = value_str
            
            if pump_id:
                data['pump_id'] = pump_id
            if light_id:
                data['light_id'] = light_id
            
            return data

    async def _trigger_state_update(self) -> None:
        """Trigger an immediate state update after a successful command.
        
        This ensures MQTT state topics reflect the new hardware state
        without waiting for the next polling cycle.
        
        Adds a configurable delay to allow the SmartTub Cloud API to process
        the command before fetching the updated state. The delay compensates
        for cloud API propagation latency.
        
        The delay can be configured via:
        - YAML: smarttub.state_update_delay_seconds (default: 2.5)
        - ENV: STATE_UPDATE_DELAY_SECONDS (range: 0.5-10.0 seconds)
        """
        if self._state_manager is None:
            logger.warning("State manager not set, cannot trigger immediate state update")
            return
        
        try:
            delay = self.config.smarttub.state_update_delay_seconds
            logger.debug(f"Triggering immediate state update after {delay}s delay")
            # Wait for SmartTub Cloud API to process the command
            # The cloud API is slow and needs time to update its state
            await asyncio.sleep(delay)
            await self._state_manager.sync_state()
            logger.debug("Immediate state update completed")
        except Exception as e:
            logger.error(f"Failed to trigger immediate state update: {e}", exc_info=True)
    
    def _execute_handler(self, handler: Callable, data: Any) -> None:
        """Queue async handler for execution in the main event loop.
        
        This is called from the MQTT callback thread, so we can't directly
        use asyncio.create_task(). Instead, we queue the handler and data
        for processing by the main event loop.
        
        Args:
            handler: Async handler function to execute
            data: Data to pass to handler
        """
        # Put handler and data in queue for processing by main event loop
        self._command_queue.put((handler, data))
        logger.debug(f"Queued command handler: {handler.__name__}")

    async def _handle_set_temperature(self, data: Any) -> None:
        """Handle set temperature command."""
        try:
            if isinstance(data, dict):
                temperature = data.get("temperature")
            else:
                temperature = float(data)

            if temperature is not None:
                await self.smarttub_client.set_temperature(temperature)
                logger.info(f"Set temperature to {temperature}°C")
                
                # Trigger immediate state update
                await self._trigger_state_update()
            else:
                logger.error("No temperature value provided in set_temperature command")
        except Exception as e:
            logger.error(f"Failed to set temperature: {e}")

    async def _handle_set_heat_mode(self, data: Any) -> None:
        """Handle set heat mode command."""
        try:
            if isinstance(data, dict):
                mode = data.get("mode")
            else:
                mode = str(data).upper()

            if mode:
                await self.smarttub_client.set_heat_mode(mode)
                logger.info(f"Set heat mode to {mode}")
                
                # Trigger immediate state update
                await self._trigger_state_update()
            else:
                logger.error("No mode value provided in set_heat_mode command")
        except Exception as e:
            logger.error(f"Failed to set heat mode: {e}")

    async def _handle_set_pump_state(self, data: Any) -> None:
        """Handle set pump state command."""
        try:
            if isinstance(data, dict):
                state = data.get("state")
            else:
                state = str(data).lower()

            if state in ["on", "off"]:
                # Extract optional pump_id injected by topic parsing
                pump_id = None
                if isinstance(data, dict):
                    pump_id = data.get('pump_id')

                await self.smarttub_client.set_pump_state(state == "on", pump_id=pump_id)
                logger.info(f"Pump control requested: {state} (pump_id={pump_id})")
                
                # Trigger immediate state update
                await self._trigger_state_update()
            else:
                logger.error(f"Invalid pump state: {state}. Must be 'on' or 'off'")
        except Exception as e:
            logger.error(f"Failed to set pump state: {e}")

    async def _handle_set_light_state(self, data: Any) -> None:
        """Handle set light state command."""
        try:
            if isinstance(data, dict):
                state = data.get("state")
                light_id = data.get("light_id")
            else:
                state = str(data).lower()
                light_id = None

            if state in ["on", "off"]:
                await self.smarttub_client.set_light_state(state == "on", light_id=light_id)
                logger.info(f"Light control requested: {state} (light_id={light_id})")
                
                # Trigger immediate state update
                await self._trigger_state_update()
            else:
                logger.error(f"Invalid light state: {state}. Must be 'on' or 'off'")
        except Exception as e:
            logger.error(f"Failed to set light state: {e}")

    async def _handle_set_light_mode(self, data: Any) -> None:
        """Handle set light mode command (e.g., OFF, WHITE, PURPLE, LowSpeedWheel, ColorWheel)."""
        try:
            if isinstance(data, dict):
                mode = data.get("mode") or data.get("value")
                light_id = data.get("light_id")
            else:
                mode = str(data).upper()
                light_id = None

            if mode:
                await self.smarttub_client.set_light_mode(mode, light_id=light_id)
                logger.info(f"Light mode control requested: {mode} (light_id={light_id})")
                
                # Trigger immediate state update
                await self._trigger_state_update()
            else:
                logger.error("No mode value provided in set_light_mode command")
        except Exception as e:
            logger.error(f"Failed to set light mode: {e}")

    async def _handle_set_light_color(self, data: Any) -> None:
        """Handle set light color command."""
        try:
            if isinstance(data, dict):
                color = data.get("color") or data.get("value")
                light_id = data.get("light_id")
            else:
                color = str(data)
                light_id = None

            if color:
                await self.smarttub_client.set_light_color(color, light_id=light_id)
                logger.info(f"Light color control requested: {color} (light_id={light_id})")
                
                # Trigger immediate state update
                await self._trigger_state_update()
            else:
                logger.error("No color value provided in set_light_color command")
        except Exception as e:
            logger.error(f"Failed to set light color: {e}")

    async def _handle_set_light_brightness(self, data: Any) -> None:
        """Handle set light brightness command."""
        try:
            if isinstance(data, dict):
                brightness = data.get("brightness") or data.get("value")
                light_id = data.get("light_id")
            else:
                brightness = int(data)
                light_id = None

            if brightness is not None and 0 <= brightness <= 100:
                await self.smarttub_client.set_light_brightness(brightness, light_id=light_id)
                logger.info(f"Light brightness control requested: {brightness}% (light_id={light_id})")
                
                # Trigger immediate state update
                await self._trigger_state_update()
            else:
                logger.error(f"Invalid brightness value: {brightness}. Must be between 0 and 100")
        except Exception as e:
            logger.error(f"Failed to set light brightness: {e}")