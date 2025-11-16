from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.config_loader import AppConfig

logger = logging.getLogger("smarttub.api")


class SmartTubClient:
    """Client wrapper for SmartTub API with polling and error handling."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._smarttub_api = None
        self._account = None
        self._spas: List[Any] = []
        self._last_error: Optional[Exception] = None

    async def initialize(self) -> None:
        """Initialize the SmartTub API connection."""
        try:
            # Import here to avoid import errors if library not installed
            from smarttub import SmartTub  # type: ignore

            self._smarttub_api = SmartTub()
            await self._smarttub_api.login(
                self.config.smarttub.email,
                self.config.smarttub.password
            )

            self._account = await self._smarttub_api.get_account()
            self._spas = await self._account.get_spas()

            # Auto-detect device ID if not configured
            if not self.config.smarttub.device_id and self._spas:
                self.config.smarttub.device_id = str(self._spas[0].id)
                logger.info(f"Auto-detected SmartTub device ID: {self.config.smarttub.device_id}")

            logger.info(f"Connected to SmartTub account with {len(self._spas)} spa(s), _spas: {self._spas}")
            self._last_error = None

        except Exception as e:
            logger.error(f"Failed to initialize SmartTub client: {e}")
            self._last_error = e
            raise

    async def get_state_snapshot(self) -> Dict[str, Any]:
        """Get current state snapshot from all spas.

        Returns:
            State snapshot with timestamp and components
        """
        if self._smarttub_api is None:
            await self.initialize()

        if not self._spas:
            # Return safe fallback state if no spas available
            return self._get_safe_fallback_snapshot()

        try:
            # For now, handle only the first spa (can be extended for multiple spas)
            spa = self._spas[0]
            status = await spa.get_status()

            # Transform SmartTub status to our snapshot format
            snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                # include spa_id at top-level so MQTTTopicMapper can publish under
                # smarttub-mqtt/<spa_id>/... as requested
                "spa_id": str(spa.id),
                "components": {}
            }

            # Map SmartTub status to our component structure
            # The status object has attributes, not dict keys
            # Extract water temperature from status.water if available (used for both spa and heater)
            water_temp = None
            if hasattr(status, 'water') and status.water:
                water_temp = getattr(status.water, 'temperature', None)
            else:
                water_temp = getattr(status, 'water_temperature', None)

            snapshot["components"]["heater"] = {
                "state": 'on' if getattr(status, 'heater', 'OFF') == 'ON' else 'off',
                # Use the normalized water_temp so heater shows the correct current temperature
                "temperature": water_temp,
                "target_temperature": getattr(status, 'set_temperature', None)
            }

            # Get detailed pump information from separate API call
            try:
                pumps_data = await spa.get_pumps()
                # spa.get_pumps() returns a list of SpaPump objects, not a dict
                if pumps_data and isinstance(pumps_data, list):
                    snapshot["components"]["pumps"] = []
                    logger.debug(f"Processing {len(pumps_data)} pump objects from API")
                    for pump in pumps_data:
                        # SpaPump object has attributes, not dict keys
                        pump_state = pump.state.name if hasattr(pump.state, 'name') else str(pump.state)
                        pump_entry = {
                            "id": pump.id,
                            "type": pump.type.name if hasattr(pump.type, 'name') else str(pump.type),
                            "state": 'running' if pump_state in ('HIGH', 'ON') else 'off',
                            "speed": 'ONE_SPEED'  # Default for most pumps
                        }
                        snapshot["components"]["pumps"].append(pump_entry)
                        logger.debug(f"Added pump {pump.id} (state={pump_state}) to snapshot")
                else:
                    logger.warning(f"No pumps data or not a list. Type: {type(pumps_data)}")
                    snapshot["components"]["pumps"] = []
            except Exception as e:
                logger.error(f"Could not get pump data: {e}", exc_info=True)
                snapshot["components"]["pumps"] = []

            # Get detailed light information from separate API call
            try:
                # Use direct API call to get raw light data with correct color values
                # The python-smarttub library's SpaLight.color returns empty dict
                lights_response = await spa.request("GET", "lights")
                lights_data = lights_response.get('lights', []) if isinstance(lights_response, dict) else []
                
                if lights_data and isinstance(lights_data, list):
                    snapshot["components"]["lights"] = []
                    logger.debug(f"Processing {len(lights_data)} light objects from API")
                    for light_dict in lights_data:
                        # Now we have raw dicts from API with correct color values
                        color_obj = light_dict.get('color', {})
                        logger.debug(f"Light color_obj: type={type(color_obj)}, value={color_obj}, isinstance_dict={isinstance(color_obj, dict)}")
                        if isinstance(color_obj, dict):
                            red = color_obj.get('red', 255)
                            green = color_obj.get('green', 255)
                            blue = color_obj.get('blue', 255)
                            logger.debug(f"Color from dict: R={red}, G={green}, B={blue}, raw={color_obj}")
                        else:
                            # Fallback if color is not a dict
                            red, green, blue = 255, 255, 255
                            logger.debug(f"Color fallback: R={red}, G={green}, B={blue}, type={type(color_obj)}")
                        hex_color = f"#{red:02x}{green:02x}{blue:02x}"
                        
                        light_mode = light_dict.get('mode', 'UNKNOWN')
                        zone = light_dict.get('zone', 0)
                        
                        
                        # Calculate brightness from RGB for FULL_DYNAMIC_RGB, else use intensity
                        if light_mode == "FULL_DYNAMIC_RGB":
                            # Brightness calculation depends on whether it's white or colored light
                            max_channel = max(red, green, blue)
                            min_channel = min(red, green, blue)
                            
                            # Detect if it's approximately white (all channels similar)
                            # White: all channels within 10% of each other
                            if max_channel > 0:
                                channel_variance = (max_channel - min_channel) / max_channel
                                is_white = channel_variance < 0.15  # Less than 15% variance = white
                                
                                if is_white:
                                    # For white light: hardware max is 85 per channel
                                    brightness = int(min(100, (max_channel / 85.0) * 100.0))
                                else:
                                    # For colored light: scale to 255 (single-channel can go higher)
                                    brightness = int(min(100, (max_channel / 255.0) * 100.0))
                            else:
                                brightness = 0
                        else:
                            # For other modes, use intensity field (unreliable but no alternative)
                            brightness = light_dict.get('intensity', 0)
                        
                        light_entry = {
                            "id": f"zone_{zone}",
                            "zone": zone,
                            "type": light_dict.get('zoneType', 'UNKNOWN'),
                            "state": 'on' if light_mode != 'OFF' else 'off',
                            "mode": light_mode,
                            "color": hex_color,
                            "brightness": brightness
                        }
                        snapshot["components"]["lights"].append(light_entry)
                        logger.debug(f"Added light zone {zone} (mode={light_mode}, brightness={brightness}%, color={hex_color}) to snapshot")
                else:
                    logger.warning(f"No lights data or not a list. Type: {type(lights_data)}")
                    snapshot["components"]["lights"] = []
            except Exception as e:
                logger.error(f"Could not get light data: {e}", exc_info=True)
                snapshot["components"]["lights"] = []

            # Add overall spa state - reuse water_temp from above
            air_temp = getattr(status, 'ambient_temperature', None)
            if air_temp == 0.0:  # API returns 0.0 when no sensor
                air_temp = None
                
            snapshot["components"]["spa"] = {
                "state": getattr(status, 'state', 'unknown'),
                "water_temperature": water_temp,
                "air_temperature": air_temp
            }

            self._last_error = None
            return snapshot

        except Exception as e:
            logger.error(f"Failed to get state snapshot: {e}")
            self._last_error = e
            return self._get_safe_fallback_snapshot()

    def _get_safe_fallback_snapshot(self) -> Dict[str, Any]:
        """Return a safe fallback snapshot when API is unavailable."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {
                "heater": {"state": "off"},
                "pump": {"state": "off"},
                "light": {"state": "off"},
                "spa": {"state": "unknown"}
            }
        }

    async def reconnect(self) -> bool:
        """Attempt to reconnect to SmartTub API.

        Returns:
            True if reconnection successful, False otherwise
        """
        try:
            await self.initialize()
            return True
        except Exception:
            return False

    async def log_spa_debug_info(self) -> None:
        """Log diagnostic information about connected Spa objects.

        This method inspects the Spa objects and logs available attributes and
        callable methods (filtered to likely control methods). It is intended
        to be run only when logging.level is debug to help diagnose available
        APIs on the upstream python-smarttub library / device.
        """
        try:
            if not self._spas:
                logger.debug("log-spa-debug-info: no spas available to inspect")
                return

            import inspect

            for spa in self._spas:
                spa_id = getattr(spa, 'id', None)
                try:
                    attrs = [a for a in dir(spa) if not a.startswith('_')]
                    methods = []
                    for a in attrs:
                        try:
                            val = getattr(spa, a)
                        except Exception:
                            continue
                        if callable(val):
                            # try to get signature when possible, but ignore failures
                            sig = None
                            try:
                                sig = str(inspect.signature(val))
                            except Exception:
                                sig = None
                            methods.append({'name': a, 'signature': sig})

                    logger.debug("spa-debug-info", extra={"spa_id": spa_id, "attributes_count": len(attrs), "methods_sample": methods[:20]})

                    # Also inspect child components (pumps/lights) if available
                    try:
                        pumps = await spa.get_pumps()
                        if pumps and isinstance(pumps, dict) and 'pumps' in pumps:
                            for p in pumps.get('pumps', [])[:10]:
                                try:
                                    # If object, list its callables
                                    if not isinstance(p, dict):
                                        pm = [x for x in dir(p) if not x.startswith('_') and callable(getattr(p, x, None))]
                                        logger.debug("spa-pump-debug", extra={"spa_id": spa_id, "pump_id": getattr(p, 'id', None), "pump_methods": pm[:20]})
                                except Exception:
                                    continue
                    except Exception:
                        # best-effort only
                        logger.debug("spa-debug-info: could not inspect pumps for spa", extra={"spa_id": spa_id})

                except Exception as e:
                    logger.debug(f"spa-debug-inspect-failed: {e}", exc_info=True)

        except Exception as e:
            logger.debug(f"log_spa_debug_info failed: {e}", exc_info=True)

    @property
    def is_connected(self) -> bool:
        """Check if client is connected to SmartTub API."""
        return self._smarttub_api is not None and self._last_error is None

    @property
    def spas(self) -> List[Any]:
        """Get list of available spas."""
        logger.info(f"spas property called, _spas: {self._spas}")
        return self._spas.copy()

    # Command methods for controlling the spa
    async def set_temperature(self, temperature_c: float) -> None:
        """Set the spa target temperature.

        Args:
            temperature_c: Target temperature in Celsius
        """
        if not self._spas:
            raise RuntimeError("No spa available for control")

        spa = self._spas[0]  # Use first spa for now
        await spa.set_temperature(temperature_c)
        logger.info(f"Set spa temperature to {temperature_c}°C")

    async def set_heat_mode(self, mode: str) -> None:
        """Set the spa heating mode.

        Args:
            mode: Heat mode (e.g., 'AUTO', 'ECONOMY', 'DAY', 'READY', 'REST')
        """
        if not self._spas:
            raise RuntimeError("No spa available for control")

        spa = self._spas[0]  # Use first spa for now

        # Map string mode to SmartTub enum
        # HeatMode is defined locally in Spa class
        heat_mode = getattr(spa, 'HeatMode', None)
        if heat_mode:
            mode_enum = getattr(heat_mode, mode.upper(), heat_mode.AUTO)
            await spa.set_heat_mode(mode_enum)
            logger.info(f"Set spa heat mode to {mode}")
        else:
            logger.error("HeatMode enum not available in Spa class")

    async def set_pump_state(self, enabled: bool, pump_id: Optional[str] = None) -> None:
        """Set the spa pump state using python-smarttub SpaPump.toggle() method.

        Args:
            enabled: True to turn pump on, False to turn off
            pump_id: Pump identifier (e.g. 'P1', 'P2', 'CP')
        """
        if not self._spas:
            raise RuntimeError("No spa available for control")

        spa = self._spas[0]
        logger.info("Attempting to set pump state", extra={"pump_id": pump_id, "enabled": enabled})

        try:
            # Get SpaPump objects from python-smarttub library
            pumps = await spa.get_pumps()
            logger.debug(f"Retrieved {len(pumps)} pump objects from spa.get_pumps()")

            # Find the target pump
            target_pump = None
            if pump_id:
                for pump in pumps:
                    if pump.id == pump_id:
                        target_pump = pump
                        break
            else:
                # No pump_id specified, use first pump
                target_pump = pumps[0] if pumps else None

            if not target_pump:
                logger.warning(f"Pump '{pump_id}' not found", extra={"available_pumps": [p.id for p in pumps]})
                return

            # Check current state (PumpState enum: OFF, LOW, HIGH)
            current_state_is_on = target_pump.state.name in ('LOW', 'HIGH', 'ON')
            logger.debug(f"Pump {target_pump.id} current state: {target_pump.state.name} (is_on={current_state_is_on})")

            # Only toggle if state needs to change
            if current_state_is_on == enabled:
                logger.info(f"Pump {target_pump.id} already in desired state ({target_pump.state.name})")
                return

            # Toggle the pump
            logger.info(f"Toggling pump {target_pump.id} from {target_pump.state.name} to {'ON' if enabled else 'OFF'}")
            
            # Use spa.request() directly instead of target_pump.toggle() to avoid
            # the AttributeError in python-smarttub's _wait_for_state_change() method
            # which tries to access state.pumps (which is None when using get_status_full)
            try:
                await spa.request("POST", f"pumps/{target_pump.id}/toggle")
                logger.info(f"Successfully sent toggle request for pump {target_pump.id}")
            except Exception as toggle_error:
                logger.error(f"Toggle request failed: {toggle_error}", exc_info=True)
                raise

        except Exception as e:
            logger.error(f"Failed to control pump: {e}", exc_info=True)

    async def set_light_state(self, enabled: bool, light_id: str | None = None) -> None:
        """Set the spa light state (ON/OFF).

        Uses direct API calls to avoid python-smarttub library bug.

        Args:
            enabled: True to turn light on, False to turn off
            light_id: Light zone ID (e.g., "zone_1" for zone 1)
        """
        if not self._spas:
            raise RuntimeError("No spa available for control")

        spa = self._spas[0]

        # Extract zone number from light_id (e.g., "zone_1" -> 1)
        zone = None
        if light_id and light_id.startswith("zone_"):
            try:
                zone = int(light_id.split("_")[1])
            except (IndexError, ValueError):
                logger.error(f"Invalid light_id format: {light_id}")
                return

        lights = await spa.get_lights()
        if not lights:
            logger.warning("No lights available to control")
            return

        # Find matching light
        target_light = None
        if zone is not None:
            target_light = next((light for light in lights if light.zone == zone), None)
        else:
            # No zone specified, use first light
            target_light = lights[0] if lights else None

        if not target_light:
            logger.warning(f"Light not found: zone={zone}")
            return

        # Set light mode (ON/OFF)
        # Use direct API to avoid python-smarttub library bug
        try:
            if enabled:
                # Get current light state to check zone type
                lights_response = await spa.request("GET", "lights")
                lights_data = lights_response.get('lights', [])
                current_light = next((l for l in lights_data if l.get('zone') == target_light.zone), None)
                
                logger.debug(f"Light ON: target_light.zone={target_light.zone}, current_light={current_light}")
                
                # Check if light supports RGB by looking at current mode
                # If mode is FULL_DYNAMIC_RGB or any RGB-capable mode, restore color
                current_mode = current_light.get('mode') if current_light else None
                is_rgb_capable = current_mode == 'FULL_DYNAMIC_RGB'
                
                if current_light and is_rgb_capable:
                    # For RGB lights: restore last color or use default white
                    color_obj = current_light.get('color', {})
                    red = color_obj.get('red', 85)
                    green = color_obj.get('green', 85)
                    blue = color_obj.get('blue', 85)
                    
                    logger.debug(f"RGB light detected (mode={current_mode}), setting RGB=({red},{green},{blue})")
                    
                    await spa.request("PATCH", f"lights/{target_light.zone}", {
                        "mode": "FULL_DYNAMIC_RGB",
                        "red": red,
                        "green": green,
                        "blue": blue
                    })
                    logger.info(f"Set RGB light zone {target_light.zone} to ON (RGB={red},{green},{blue})")
                else:
                    logger.debug(f"Non-RGB light: current_light exists={current_light is not None}, mode={current_mode}")
                    # For non-RGB lights: use WHITE mode
                    await spa.request("PATCH", f"lights/{target_light.zone}", {
                        "mode": "WHITE",
                        "intensity": 50
                    })
                    logger.info(f"Set light zone {target_light.zone} to ON (WHITE, 50%)")
            else:
                # Turn off
                await spa.request("PATCH", f"lights/{target_light.zone}", {
                    "mode": "OFF",
                    "intensity": 0
                })
                logger.info(f"Set light zone {target_light.zone} to OFF")
        except Exception as e:
            logger.error(f"Failed to set light state for zone {target_light.zone}: {e}")

    async def set_light_mode(self, mode: str, light_id: str | None = None) -> None:
        """Set the spa light mode.

        Args:
            mode: Light mode (e.g., OFF, WHITE, PURPLE, RED, COLOR_WHEEL, etc.)
            light_id: Light zone ID
        """
        if not self._spas:
            raise RuntimeError("No spa available for control")

        spa = self._spas[0]

        # Extract zone
        zone = None
        if light_id and light_id.startswith("zone_"):
            try:
                zone = int(light_id.split("_")[1])
            except (IndexError, ValueError):
                logger.error(f"Invalid light_id format: {light_id}")
                return

        lights = await spa.get_lights()
        if not lights:
            logger.warning("No lights available to control")
            return

        target_light = None
        if zone is not None:
            target_light = next((light for light in lights if light.zone == zone), None)
        else:
            target_light = lights[0] if lights else None

        if not target_light:
            logger.warning(f"Light not found: zone={zone}")
            return

        # Convert mode string and set via direct API to avoid python-smarttub library bug
        try:
            mode_upper = mode.upper()
            intensity = 0 if mode_upper == "OFF" else 50
            
            await spa.request("PATCH", f"lights/{target_light.zone}", {
                "mode": mode_upper,
                "intensity": intensity
            })
            logger.info(f"Set light zone {target_light.zone} mode to {mode_upper} (intensity={intensity})")
        except Exception as e:
            logger.error(f"Failed to set light mode for zone {target_light.zone}: {e}", exc_info=True)

    async def set_light_color(self, color: str, light_id: str | None = None) -> None:
        """Set the spa light color.

        Supports multiple formats:
        - RGB decimal: "255,0,0" or "255 0 0"
        - RGB hex: "#ff0000" or "ff0000"
        - RGB JSON: '{"red":255,"green":0,"blue":0}' or '{"r":255,"g":0,"b":0}'
        - Color name: "RED", "BLUE", etc. (sets light mode, not RGB)

        Args:
            color: Color value in one of the supported formats
            light_id: Light zone ID (e.g., "zone_1")
        """
        if not self._spas:
            raise RuntimeError("No spa available for control")

        spa = self._spas[0]

        # Extract zone
        zone = None
        if light_id and light_id.startswith("zone_"):
            try:
                zone = int(light_id.split("_")[1])
            except (IndexError, ValueError):
                logger.error(f"Invalid light_id format: {light_id}")
                return

        # Try to parse as RGB value
        rgb = self._parse_rgb_color(color)
        
        if rgb:
            # RGB value detected - use direct API call for FULL_DYNAMIC_RGB
            if zone is None:
                logger.error("Zone required for RGB color control")
                return
            
            try:
                await spa.request("PATCH", f"lights/{zone}", {
                    "color": {"red": rgb[0], "green": rgb[1], "blue": rgb[2]}
                })
                logger.info(f"Set light zone {zone} to RGB({rgb[0]}, {rgb[1]}, {rgb[2]})")
            except Exception as e:
                logger.error(f"Failed to set RGB color for zone {zone}: {e}")
        else:
            # Color name - use legacy mode switching
            color_map = {
                "RED": "RED",
                "BLUE": "BLUE",
                "GREEN": "GREEN",
                "PURPLE": "PURPLE",
                "ORANGE": "ORANGE",
                "YELLOW": "YELLOW",
                "AQUA": "AQUA",
                "WHITE": "WHITE",
                "AMBER": "AMBER",
            }
            mode = color_map.get(color.upper(), color.upper())
            await self.set_light_mode(mode, light_id)

    def _parse_rgb_color(self, color: str) -> tuple[int, int, int] | None:
        """Parse RGB color from various formats.
        
        Supported formats:
        - Decimal: "255,0,0" or "255 0 0"
        - Hex: "#ff0000" or "ff0000"
        - JSON: '{"red":255,"green":0,"blue":0}' or '{"r":255,"g":0,"b":0}'
        
        Returns:
            Tuple of (r, g, b) values (0-255) or None if not RGB format
        """
        import json
        import re
        
        color = color.strip()
        
        # Try JSON format
        if color.startswith('{'):
            try:
                data = json.loads(color)
                r = data.get('red') or data.get('r')
                g = data.get('green') or data.get('g')
                b = data.get('blue') or data.get('b')
                if r is not None and g is not None and b is not None:
                    return (self._clamp_rgb(int(r)), self._clamp_rgb(int(g)), self._clamp_rgb(int(b)))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        
        # Try hex format
        if color.startswith('#'):
            color = color[1:]
        if re.match(r'^[0-9a-fA-F]{6}$', color):
            try:
                r = int(color[0:2], 16)
                g = int(color[2:4], 16)
                b = int(color[4:6], 16)
                return (r, g, b)
            except ValueError:
                pass
        
        # Try decimal format (comma or space separated)
        parts = re.split(r'[,\s]+', color)
        if len(parts) == 3:
            try:
                r, g, b = [int(p.strip()) for p in parts]
                return (self._clamp_rgb(r), self._clamp_rgb(g), self._clamp_rgb(b))
            except ValueError:
                pass
        
        return None
    
    def _clamp_rgb(self, value: int) -> int:
        """Clamp RGB value to 0-255 range."""
        return max(0, min(255, value))

    async def set_light_brightness(self, brightness: int, light_id: str | None = None) -> None:
        """Set the spa light brightness using RGB scaling.
        
        For FULL_DYNAMIC_RGB mode:
        - Scales current RGB values proportionally
        - Uses white calibration if currently off (all RGB=0)
        
        For other modes:
        - Falls back to intensity field (known to be unreliable)

        Args:
            brightness: Brightness level (0-100)
            light_id: Light zone ID
        """
        if not self._spas:
            raise RuntimeError("No spa available for control")

        spa = self._spas[0]

        # Extract zone
        zone = None
        if light_id and light_id.startswith("zone_"):
            try:
                zone = int(light_id.split("_")[1])
            except (IndexError, ValueError):
                logger.error(f"Invalid light_id format: {light_id}")
                return

        # Get current light state via direct API (library objects don't have color data)
        lights_response = await spa.request("GET", "lights")
        lights_data = lights_response.get('lights', []) if isinstance(lights_response, dict) else []
        
        if not lights_data:
            logger.warning("No lights available to control")
            return

        target_light = None
        if zone is not None:
            target_light = next((light for light in lights_data if light.get('zone') == zone), None)
        else:
            target_light = lights_data[0] if lights_data else None

        if not target_light:
            logger.warning(f"Light not found: zone={zone}")
            return

        current_mode = target_light.get('mode', 'UNKNOWN')
        
        # For FULL_DYNAMIC_RGB: Use RGB-based brightness control with hardware calibration
        if current_mode == "FULL_DYNAMIC_RGB":
            color_obj = target_light.get('color', {})
            current_r = color_obj.get('red', 0)
            current_g = color_obj.get('green', 0)
            current_b = color_obj.get('blue', 0)
            
            # Hardware limits RGB to ~85 at "100% brightness"
            hardware_max_rgb = 85
            current_max_rgb = max(current_r, current_g, current_b)
            
            # Calculate current brightness in hardware scale (0-100%)
            if current_max_rgb > 0:
                current_brightness = (current_max_rgb / hardware_max_rgb) * 100.0
            else:
                current_brightness = 0
            
            if current_brightness > 0:
                # Scale RGB proportionally based on hardware range
                target_max_rgb = int((brightness / 100.0) * hardware_max_rgb)
                scale_factor = target_max_rgb / current_max_rgb
                new_r = int(min(hardware_max_rgb, current_r * scale_factor))
                new_g = int(min(hardware_max_rgb, current_g * scale_factor))
                new_b = int(min(hardware_max_rgb, current_b * scale_factor))
            else:
                # Currently off - use white calibration or default white
                white_rgb = self._get_white_calibration(zone)
                target_max_rgb = int((brightness / 100.0) * hardware_max_rgb)
                # Scale white to hardware range
                max_white = max(white_rgb)
                if max_white > 0:
                    scale = target_max_rgb / max_white
                    new_r = int(min(hardware_max_rgb, white_rgb[0] * scale))
                    new_g = int(min(hardware_max_rgb, white_rgb[1] * scale))
                    new_b = int(min(hardware_max_rgb, white_rgb[2] * scale))
                else:
                    # Fallback to equal white
                    new_r = new_g = new_b = target_max_rgb
            
            try:
                await spa.request("PATCH", f"lights/{zone}", {
                    "color": {"red": new_r, "green": new_g, "blue": new_b}
                })
                logger.info(f"Set light zone {zone} brightness to {brightness}% via RGB({new_r}, {new_g}, {new_b})")
            except Exception as e:
                logger.error(f"Failed to set RGB brightness for zone {zone}: {e}")
        else:
            # For other modes: Use direct API call (intensity field is unreliable but no alternative)
            try:
                await spa.request("PATCH", f"lights/{zone}", {
                    "mode": mode_name,
                    "intensity": brightness
                })
                logger.info(f"Set light zone {zone} brightness to {brightness}% via intensity field (mode={mode_name}, unreliable)")
            except Exception as e:
                logger.error(f"Failed to set brightness for zone {zone}: {e}")

    def _get_white_calibration(self, zone: int | None) -> tuple[int, int, int]:
        """Get white calibration RGB values for a zone.
        
        Returns calibrated white RGB or default (255, 255, 255).
        """
        # TODO: Load from discovered_items.yaml when white calibration is implemented
        return (255, 255, 255)