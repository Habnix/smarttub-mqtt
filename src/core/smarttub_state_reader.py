"""Read SmartTub state and translate it into the MQTT snapshot format.

The reader owns observation and normalization of API state. Connection and
command operations remain on SmartTubClient.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.core.pump_model import (
    enum_name,
    normalize_pump_role,
    normalize_pump_state,
    normalize_speed_capability,
    supported_speeds,
)
from src.core.state_models import LightComponent, PumpComponent, StateSnapshot

logger = logging.getLogger("smarttub.api")


class SmartTubStateReader:
    """Build a stable state snapshot from a SmartTub client."""

    def __init__(self, client: Any):
        self.client = client
        self.gateway = client.gateway

    async def get_state_snapshot(self) -> StateSnapshot:
        """Get the current state snapshot from the selected spa.

        Returns:
            State snapshot with timestamp and components
        """
        if self.client._smarttub_api is None:
            await self.client.initialize()

        if not self.client._spas:
            raise RuntimeError("No configured SmartTub spa is available")

        try:
            # Initialization keeps exactly the spa selected for this instance.
            spa = self.client._spas[0]
            status = await spa.get_status()

            # Transform SmartTub status to our snapshot format
            snapshot: StateSnapshot = {
                "timestamp": datetime.now(UTC).isoformat(),
                # include spa_id at top-level so MQTTTopicMapper can publish under
                # smarttub-mqtt/<spa_id>/... as requested
                "spa_id": str(spa.id),
                "components": {},
            }

            # Map SmartTub status to our component structure
            # The status object has attributes, not dict keys
            # Extract water temperature from status.water if available (used for both spa and heater)
            water_temp = None
            if hasattr(status, "water") and status.water:
                water_temp = getattr(status.water, "temperature", None)
            else:
                water_temp = getattr(status, "water_temperature", None)

            snapshot["components"]["heater"] = {
                "state": "on" if getattr(status, "heater", "OFF") == "ON" else "off",
                # Use the normalized water_temp so heater shows the correct current temperature
                "temperature": water_temp,
                "target_temperature": getattr(status, "set_temperature", None),
            }

            # python-smarttub 0.0.48 exposes primary filtration, including
            # ECO_MODE. Keep this separate from the heater's ECONOMY mode.
            primary_filtration = getattr(status, "primary_filtration", None)
            if primary_filtration is not None:
                snapshot["components"]["filtration"] = {
                    "mode": self.client._enum_name(
                        getattr(primary_filtration, "mode", None)
                    ),
                    "cycle": getattr(primary_filtration, "cycle", None),
                    "duration": getattr(primary_filtration, "duration", None),
                    "start_hour": getattr(primary_filtration, "start_hour", None),
                    "status": self.client._enum_name(
                        getattr(primary_filtration, "status", None)
                    ),
                    "supported_modes": self.client._filtration_modes(
                        primary_filtration
                    ),
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
                        raw_state = enum_name(getattr(pump, "state", None))
                        raw_type = enum_name(getattr(pump, "type", None))
                        raw_speed_capability = enum_name(getattr(pump, "speed", None))
                        pump_state, current_speed = normalize_pump_state(
                            getattr(pump, "state", None)
                        )
                        pump_role = normalize_pump_role(getattr(pump, "type", None))
                        speed_capability = normalize_speed_capability(
                            getattr(pump, "speed", None)
                        )
                        pump_entry: PumpComponent = {
                            "id": str(pump.id),
                            "type": pump_role,
                            "state": pump_state,
                            "speed": current_speed,
                            "speed_capability": speed_capability,
                            "supported_speeds": supported_speeds(speed_capability),
                            "raw_state": raw_state,
                            "raw_type": raw_type,
                            "raw_speed_capability": raw_speed_capability,
                        }
                        snapshot["components"]["pumps"].append(pump_entry)
                        logger.debug(
                            "Added pump %s (state=%s, speed=%s, capability=%s) "
                            "to snapshot",
                            pump.id,
                            pump_state,
                            current_speed,
                            speed_capability,
                        )
                else:
                    logger.warning(
                        f"No pumps data or not a list. Type: {type(pumps_data)}"
                    )
                    snapshot["components"]["pumps"] = []
            except Exception as exc:
                logger.exception("Could not get pump data")
                raise RuntimeError("Could not read SmartTub pump state") from exc

            # Get detailed light information from separate API call
            try:
                # Use direct API call to get raw light data with correct color values
                # The python-smarttub library's SpaLight.color returns empty dict
                lights_data = await self.gateway.get_raw_lights(spa)

                if lights_data and isinstance(lights_data, list):
                    snapshot["components"]["lights"] = []
                    logger.debug(
                        f"Processing {len(lights_data)} light objects from API"
                    )
                    for light_dict in lights_data:
                        # Now we have raw dicts from API with correct color values
                        color_obj = light_dict.get("color", {})
                        logger.debug(
                            "Light color payload shape: type=%s, mapping=%s",
                            type(color_obj).__name__,
                            isinstance(color_obj, dict),
                        )
                        if isinstance(color_obj, dict):
                            red = color_obj.get("red", 255)
                            green = color_obj.get("green", 255)
                            blue = color_obj.get("blue", 255)
                            logger.debug("Normalized light RGB channels")
                        else:
                            # Fallback if color is not a dict
                            red, green, blue = 255, 255, 255
                            logger.debug(
                                f"Color fallback: R={red}, G={green}, B={blue}, type={type(color_obj)}"
                            )
                        hex_color = f"#{red:02x}{green:02x}{blue:02x}"

                        light_mode = light_dict.get("mode", "UNKNOWN")
                        zone = light_dict.get("zone", 0)

                        # Calculate brightness from RGB for FULL_DYNAMIC_RGB, else use intensity
                        if light_mode == "FULL_DYNAMIC_RGB":
                            # Brightness calculation depends on whether it's white or colored light
                            max_channel = max(red, green, blue)
                            min_channel = min(red, green, blue)

                            # Detect if it's approximately white (all channels similar)
                            # White: all channels within 10% of each other
                            if max_channel > 0:
                                channel_variance = (
                                    max_channel - min_channel
                                ) / max_channel
                                is_white = (
                                    channel_variance < 0.15
                                )  # Less than 15% variance = white

                                if is_white:
                                    # For white light: hardware max is 85 per channel
                                    brightness = int(
                                        min(100, (max_channel / 85.0) * 100.0)
                                    )
                                else:
                                    # For colored light: scale to 255 (single-channel can go higher)
                                    brightness = int(
                                        min(100, (max_channel / 255.0) * 100.0)
                                    )
                            else:
                                brightness = 0
                        else:
                            # For other modes, use intensity field (unreliable but no alternative)
                            brightness = light_dict.get("intensity", 0)

                        light_entry: LightComponent = {
                            "id": f"zone_{zone}",
                            "zone": zone,
                            "type": light_dict.get("zoneType", "UNKNOWN"),
                            "state": "on" if light_mode != "OFF" else "off",
                            "mode": light_mode,
                            "color": hex_color,
                            "brightness": brightness,
                            # python-smarttub 0.0.48 exposes this read-only
                            # field for color-changing lights.
                            "cycle_speed": light_dict.get(
                                "cycleSpeed", light_dict.get("cycle_speed")
                            ),
                        }
                        snapshot["components"]["lights"].append(light_entry)
                        logger.debug(
                            f"Added light zone {zone} (mode={light_mode}, brightness={brightness}%, color={hex_color}) to snapshot"
                        )
                else:
                    logger.warning(
                        f"No lights data or not a list. Type: {type(lights_data)}"
                    )
                    snapshot["components"]["lights"] = []
                snapshot["components"]["lights"].sort(
                    key=lambda light: (
                        int(light.get("zone", 0))
                        if str(light.get("zone", "")).isdigit()
                        else 0,
                        str(light.get("id", "")),
                    )
                )
            except Exception as exc:
                logger.exception("Could not get light data")
                raise RuntimeError("Could not read SmartTub light state") from exc

            # Add overall spa state - reuse water_temp from above
            air_temp = getattr(status, "ambient_temperature", None)
            if air_temp == 0.0:  # API returns 0.0 when no sensor
                air_temp = None

            snapshot["components"]["spa"] = {
                "state": getattr(status, "state", "unknown"),
                "water_temperature": water_temp,
                "air_temperature": air_temp,
            }

            self.client._last_error = None
            return snapshot

        except Exception as exc:
            logger.error("Failed to get state snapshot: %s", exc)
            self.client._last_error = exc
            raise
