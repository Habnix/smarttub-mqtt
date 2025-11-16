from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.core.config_loader import AppConfig
from src.core.smarttub_client import SmartTubClient
from src.mqtt.topic_mapper import MQTTTopicMapper

logger = logging.getLogger("smarttub.core")


class SpaCapabilities:
    """Represents the capabilities of a SmartTub spa."""

    def __init__(self, spa_id: str):
        self.spa_id = spa_id
        self.discovered_at = datetime.now(timezone.utc)
        self.last_updated = datetime.now(timezone.utc)
        self.firmware_version: Optional[str] = None
        self.model: Optional[str] = None
        self.brand: Optional[str] = None

        # Component capabilities
        self.heater_supported = False
        self.heater_temperature_range: Optional[Dict[str, float]] = None
        self.heater_modes: List[str] = []

        self.pump_supported = False
        self.pump_count = 0
        self.pump_speeds: List[str] = []

        self.light_supported = False
        self.light_colors: List[str] = []
        self.light_modes: List[str] = []  # Available light modes
        self.light_brightness_supported = False

        # Advanced features
        self.uv_supported = False
        self.ozone_supported = False
        self.nano_supported = False
        self.chromazon_supported = False

        # Water care
        self.water_care_supported = False
        self.ph_monitoring = False
        self.orp_monitoring = False
        self.turbidity_monitoring = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert capabilities to dictionary for serialization."""
        return {
            "spa_id": self.spa_id,
            "discovered_at": self.discovered_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "firmware_version": self.firmware_version,
            "model": self.model,
            "brand": self.brand,
            "components": {
                "heater": {
                    "supported": self.heater_supported,
                    "temperature_range": self.heater_temperature_range,
                    "modes": self.heater_modes,
                },
                "pump": {
                    "supported": self.pump_supported,
                    "count": self.pump_count,
                    "speeds": self.pump_speeds,
                },
                "light": {
                    "supported": self.light_supported,
                    "colors": self.light_colors,
                    "modes": self.light_modes,
                    "brightness_supported": self.light_brightness_supported,
                },
            },
            "advanced_features": {
                "uv": self.uv_supported,
                "ozone": self.ozone_supported,
                "nano": self.nano_supported,
                "chromazon": self.chromazon_supported,
            },
            "water_care": {
                "supported": self.water_care_supported,
                "ph_monitoring": self.ph_monitoring,
                "orp_monitoring": self.orp_monitoring,
                "turbidity_monitoring": self.turbidity_monitoring,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SpaCapabilities:
        """Create capabilities from dictionary."""
        spa_id = data["spa_id"]
        caps = cls(spa_id)

        caps.discovered_at = datetime.fromisoformat(data["discovered_at"])
        caps.last_updated = datetime.fromisoformat(data["last_updated"])
        caps.firmware_version = data.get("firmware_version")
        caps.model = data.get("model")
        caps.brand = data.get("brand")

        components = data.get("components", {})
        heater = components.get("heater", {})
        caps.heater_supported = heater.get("supported", False)
        caps.heater_temperature_range = heater.get("temperature_range")
        caps.heater_modes = heater.get("modes", [])

        pump = components.get("pump", {})
        caps.pump_supported = pump.get("supported", False)
        caps.pump_count = pump.get("count", 0)
        caps.pump_speeds = pump.get("speeds", [])

        light = components.get("light", {})
        caps.light_supported = light.get("supported", False)
        caps.light_colors = light.get("colors", [])
        caps.light_modes = light.get("modes", [])
        caps.light_brightness_supported = light.get("brightness_supported", False)

        advanced = data.get("advanced_features", {})
        caps.uv_supported = advanced.get("uv", False)
        caps.ozone_supported = advanced.get("ozone", False)
        caps.nano_supported = advanced.get("nano", False)
        caps.chromazon_supported = advanced.get("chromazon", False)

        water_care = data.get("water_care", {})
        caps.water_care_supported = water_care.get("supported", False)
        caps.ph_monitoring = water_care.get("ph_monitoring", False)
        caps.orp_monitoring = water_care.get("orp_monitoring", False)
        caps.turbidity_monitoring = water_care.get("turbidity_monitoring", False)

        return caps


class CapabilityDetector:
    """Detects and caches SmartTub spa capabilities dynamically."""

    def __init__(
        self,
        config: AppConfig,
        smarttub_client: SmartTubClient,
        topic_mapper: Optional[MQTTTopicMapper] = None,
    ):
        self.config = config
        self.smarttub_client = smarttub_client
        self.topic_mapper = topic_mapper
        self._capabilities_cache: Dict[str, SpaCapabilities] = {}
        self._cache_expiry_seconds = config.capability.cache_expiry_seconds
        self._refresh_interval_seconds = config.capability.refresh_interval_seconds

    async def detect_capabilities(
        self, spa_id: str, force_refresh: bool = False
    ) -> SpaCapabilities:
        """Detect capabilities for a specific spa.

        Args:
            spa_id: ID of the spa to detect capabilities for
            force_refresh: Force refresh even if cached

        Returns:
            SpaCapabilities object with detected features
        """
        # Check cache first
        if not force_refresh and spa_id in self._capabilities_cache:
            cached = self._capabilities_cache[spa_id]
            if not self._is_cache_expired(cached):
                logger.debug(f"Using cached capabilities for spa {spa_id}")
                return cached

        logger.info(f"Detecting capabilities for spa {spa_id}")

        try:
            # Get spa information from SmartTub client
            spas = self.smarttub_client.spas
            spa_data = next((spa for spa in spas if str(spa.id) == spa_id), None)

            if not spa_data:
                raise ValueError(f"Spa {spa_id} not found")

            # Create capabilities object
            capabilities = SpaCapabilities(spa_id)

            # Extract basic spa information
            capabilities.model = getattr(spa_data, "model", None)
            capabilities.brand = getattr(spa_data, "brand", None)

            # Get detailed status to detect capabilities
            status = await spa_data.get_status()

            # Detect heater capabilities
            await self._detect_heater_capabilities(capabilities, status)

            # Detect pump capabilities
            await self._detect_pump_capabilities(capabilities, spa_data)

            # Detect light capabilities
            await self._detect_light_capabilities(capabilities, spa_data)

            # Load detected_modes from discovered_items.yaml if available
            await self._load_detected_modes_from_yaml(capabilities, spa_id)

            # Detect advanced features
            await self._detect_advanced_features(capabilities, status)

            # Detect water care capabilities
            await self._detect_water_care_capabilities(capabilities, status)

            # Update timestamps
            capabilities.last_updated = datetime.now(timezone.utc)

            # Cache the results
            self._capabilities_cache[spa_id] = capabilities

            # Publish capability meta to MQTT if topic_mapper is available
            if self.topic_mapper:
                capability_profile = self.get_capability_profile(spa_id)
                # Publish capability meta split into individual entries so consumers
                # can subscribe to specific fields; keep compatibility for older
                # callers by having topic_mapper also provide an aggregated message.
                messages = self.topic_mapper.publish_capability_meta_entries(
                    spa_id, capability_profile
                )
                # Also publish legacy aggregated message for backward compatibility
                legacy = self.topic_mapper.publish_capability_meta(
                    spa_id, capability_profile
                )
                messages.append(legacy)
                self.topic_mapper.publish_messages(messages)
                logger.debug(f"Published capability meta entries for spa {spa_id}")

            logger.info(f"Successfully detected capabilities for spa {spa_id}")
            return capabilities

        except Exception as e:
            logger.error(f"Failed to detect capabilities for spa {spa_id}: {e}")
            # Return minimal capabilities on error
            minimal_caps = self._get_minimal_capabilities(spa_id)
            # Cache minimal capabilities to avoid repeated API calls on error
            self._capabilities_cache[spa_id] = minimal_caps
            return minimal_caps

    async def _detect_heater_capabilities(
        self, capabilities: SpaCapabilities, status: Any
    ) -> None:
        """Detect heater-related capabilities."""
        try:
            # Check if heater exists and is functional
            heater_present = (
                getattr(status, "heater1Present", "PRESENT") != "NOT_PRESENT"
            )

            if heater_present:
                capabilities.heater_supported = True

                # Try to detect temperature range (this might be model-specific)
                # For now, use standard ranges based on model
                if capabilities.model:
                    if "low" in capabilities.model.lower():
                        capabilities.heater_temperature_range = {
                            "min": 20.0,
                            "max": 35.0,
                        }
                    else:
                        capabilities.heater_temperature_range = {
                            "min": 20.0,
                            "max": 40.0,
                        }

                # Detect available heat modes
                capabilities.heater_modes = ["AUTO", "ECONOMY", "DAY", "READY", "REST"]

        except Exception as e:
            logger.debug(f"Could not detect heater capabilities: {e}")

    async def _detect_pump_capabilities(
        self, capabilities: SpaCapabilities, spa_data: Any
    ) -> None:
        """Detect pump-related capabilities."""
        try:
            # Try to get pumps
            pumps = await spa_data.get_pumps()

            if pumps and len(pumps) > 0:
                capabilities.pump_supported = True
                capabilities.pump_count = len(pumps)

                # Detect pump speeds (simplified)
                capabilities.pump_speeds = ["off", "low", "high"]

        except Exception as e:
            logger.debug(f"Could not detect pump capabilities: {e}")

    async def _detect_light_capabilities(
        self, capabilities: SpaCapabilities, spa_data: Any
    ) -> None:
        """Detect light-related capabilities."""
        try:
            # Try to get lights
            lights = await spa_data.get_lights()

            if lights and len(lights) > 0:
                capabilities.light_supported = True

                # Basic color support
                capabilities.light_colors = ["white", "blue", "green", "red", "purple"]

                # Get all available light modes from python-smarttub
                try:
                    import smarttub

                    capabilities.light_modes = [
                        mode.name for mode in smarttub.SpaLight.LightMode
                    ]
                except Exception as e:
                    logger.debug(f"Could not get light modes from python-smarttub: {e}")
                    # Fallback to known modes
                    capabilities.light_modes = [
                        "PURPLE",
                        "ORANGE",
                        "RED",
                        "YELLOW",
                        "GREEN",
                        "AQUA",
                        "BLUE",
                        "WHITE",
                        "AMBER",
                        "HIGH_SPEED_COLOR_WHEEL",
                        "HIGH_SPEED_WHEEL",
                        "LOW_SPEED_WHEEL",
                        "FULL_DYNAMIC_RGB",
                        "AUTO_TIMER_EXTERIOR",
                        "PARTY",
                        "COLOR_WHEEL",
                        "OFF",
                        "ON",
                    ]

                # Assume brightness control is available
                capabilities.light_brightness_supported = True

        except Exception as e:
            logger.debug(f"Could not detect light capabilities: {e}")

    async def _detect_advanced_features(
        self, capabilities: SpaCapabilities, status: Any
    ) -> None:
        """Detect advanced spa features."""
        try:
            # Check for UV system
            capabilities.uv_supported = getattr(status, "uv", "OFF") != "NOT_SUPPORTED"

            # Check for ozone system
            capabilities.ozone_supported = (
                getattr(status, "ozone", "OFF") != "NOT_SUPPORTED"
            )

            # Check for nano system (based on model or status)
            nano_status = getattr(status, "nanoStatus", "OFF")
            capabilities.nano_supported = nano_status != "NOT_SUPPORTED"

            # Check for Chromazon (based on model)
            if capabilities.model and "chromazon" in capabilities.model.lower():
                capabilities.chromazon_supported = True

        except Exception as e:
            logger.debug(f"Could not detect advanced features: {e}")

    async def _detect_water_care_capabilities(
        self, capabilities: SpaCapabilities, status: Any
    ) -> None:
        """Detect water care and monitoring capabilities."""
        try:
            # Check water sensors
            water = getattr(status, "water", None)

            if water:
                capabilities.ph_monitoring = getattr(water, "ph", None) is not None
                capabilities.orp_monitoring = (
                    getattr(water, "oxidationReductionPotential", None) is not None
                )
                capabilities.turbidity_monitoring = (
                    getattr(water, "turbidity", None) is not None
                )

                capabilities.water_care_supported = (
                    capabilities.ph_monitoring
                    or capabilities.orp_monitoring
                    or capabilities.turbidity_monitoring
                )
            else:
                capabilities.water_care_supported = False
                capabilities.ph_monitoring = False
                capabilities.orp_monitoring = False
                capabilities.turbidity_monitoring = False

        except Exception as e:
            logger.debug(f"Could not detect water care capabilities: {e}")
            capabilities.water_care_supported = False
            capabilities.ph_monitoring = False
            capabilities.orp_monitoring = False
            capabilities.turbidity_monitoring = False

    async def _load_detected_modes_from_yaml(
        self, capabilities: SpaCapabilities, spa_id: str
    ) -> None:
        """Load detected_modes from discovered_items.yaml if available.

        This reads the actual tested/detected modes from the YAML file
        and uses them instead of the default list of all possible modes.
        """
        try:
            # Try multiple paths where the YAML might be
            yaml_paths = [
                Path("/config/discovered_items.yaml"),
                Path("config/discovered_items.yaml"),
                Path("discovered_items.yaml"),
            ]

            yaml_path = None
            for path in yaml_paths:
                if path.exists():
                    yaml_path = path
                    break

            if not yaml_path:
                logger.debug("discovered_items.yaml not found, using default modes")
                return

            # Load YAML file
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)

            if not data or "discovered_items" not in data:
                return

            # Get spa data
            spa_data = data["discovered_items"].get(spa_id)
            if not spa_data:
                return

            # Get lights data
            lights = spa_data.get("lights", [])
            if not lights:
                return

            # Collect all detected modes from all light zones
            detected_modes = set()
            for light in lights:
                modes = light.get("detected_modes", [])
                detected_modes.update(modes)

            # If we found detected modes, use them instead of the default list
            if detected_modes:
                capabilities.light_modes = sorted(list(detected_modes))
                logger.info(
                    f"Loaded {len(detected_modes)} detected light modes from YAML for spa {spa_id}"
                )

        except Exception as e:
            logger.debug(f"Could not load detected_modes from YAML: {e}")

    def _is_cache_expired(self, capabilities: SpaCapabilities) -> bool:
        """Check if cached capabilities have expired."""
        now = datetime.now(timezone.utc)
        age_seconds = (now - capabilities.last_updated).total_seconds()
        return age_seconds > self._cache_expiry_seconds

    def _get_minimal_capabilities(self, spa_id: str) -> SpaCapabilities:
        """Get minimal capabilities when detection fails."""
        caps = SpaCapabilities(spa_id)
        # Assume basic features are supported as fallback
        caps.heater_supported = True
        caps.pump_supported = True
        caps.light_supported = True
        return caps

    def get_cached_capabilities(self, spa_id: str) -> Optional[SpaCapabilities]:
        """Get cached capabilities for a spa."""
        return self._capabilities_cache.get(spa_id)

    def clear_cache(self, spa_id: Optional[str] = None) -> None:
        """Clear capability cache.

        Args:
            spa_id: Specific spa ID to clear, or None to clear all
        """
        if spa_id:
            self._capabilities_cache.pop(spa_id, None)
        else:
            self._capabilities_cache.clear()

    async def refresh_all_capabilities(self) -> None:
        """Refresh capabilities for all known spas and publish to MQTT."""
        for spa_id in list(self._capabilities_cache.keys()):
            try:
                await self.detect_capabilities(spa_id, force_refresh=True)

                # Publish capability meta to MQTT if topic_mapper is available
                if self.topic_mapper:
                    capability_profile = self.get_capability_profile(spa_id)
                    messages = self.topic_mapper.publish_capability_meta_entries(
                        spa_id, capability_profile
                    )
                    legacy = self.topic_mapper.publish_capability_meta(
                        spa_id, capability_profile
                    )
                    messages.append(legacy)
                    self.topic_mapper.publish_messages(messages)
                    logger.debug(f"Published capability meta entries for spa {spa_id}")

            except Exception as e:
                logger.error(f"Failed to refresh capabilities for spa {spa_id}: {e}")

    def get_capability_profile(self, spa_id: str) -> Dict[str, Any]:
        """Get a simplified capability profile for UI/API consumption."""
        capabilities = self.get_cached_capabilities(spa_id)
        if not capabilities:
            return {"spa_id": spa_id, "status": "unknown"}

        return {
            "spa_id": spa_id,
            "status": "detected",
            "model": capabilities.model,
            "brand": capabilities.brand,
            "supported_features": {
                "heater": capabilities.heater_supported,
                "pump": capabilities.pump_supported,
                "light": capabilities.light_supported,
                "water_care": capabilities.water_care_supported,
                "advanced": any(
                    [
                        capabilities.uv_supported,
                        capabilities.ozone_supported,
                        capabilities.nano_supported,
                        capabilities.chromazon_supported,
                    ]
                ),
            },
            "lights": {
                "modes": capabilities.light_modes,
                "colors": capabilities.light_colors,
                "brightness_supported": capabilities.light_brightness_supported,
            }
            if capabilities.light_supported
            else None,
            "last_updated": capabilities.last_updated.isoformat(),
        }
