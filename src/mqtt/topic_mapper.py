from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List

import yaml
from src.core.config_loader import AppConfig

logger = logging.getLogger("smarttub.mqtt.mapper")


class MQTTMessage:
    """Represents an MQTT message to be published."""

    def __init__(self, topic: str, payload: str, qos: int = 1, retain: bool = True):
        self.topic = topic
        self.payload = payload
        self.qos = qos
        self.retain = retain


class MQTTTopicMapper:
    """Maps SmartTub state snapshots to MQTT topic/payload messages."""

    def __init__(self, config: AppConfig, mqtt_client: Any):
        self.config = config
        self.mqtt_client = mqtt_client

    def publish_state_snapshot(self, snapshot: dict[str, Any]) -> List[MQTTMessage]:
        """Convert a state snapshot into MQTT messages for publishing.
        
        T053: All state topics publish RAW data (plain values without JSON wrapping).
        - State/value topics: Plain strings (e.g., "on", "38.5", "running")
        - Meta topics: JSON allowed (for discovery, capabilities, documentation)
        - No units in payloads (e.g., "38.5" not "38.5°C")
        - No complex JSON objects in state topics

        Args:
            snapshot: State snapshot with timestamp and components

        Returns:
            List of MQTT messages to publish (all with RAW payloads except meta topics)
        """
        messages = []
        # Determine spa-specific base topic: prefer spa_id from snapshot if present,
        # else fall back to configured device_id. If neither available, use configured base_topic.
        spa_id = snapshot.get("spa_id") or getattr(self.config.smarttub, "device_id", None)
        if spa_id:
            base_topic = f"{self.config.mqtt.base_topic}/{spa_id}"
        else:
            base_topic = self.config.mqtt.base_topic
        timestamp = snapshot.get("timestamp", "")

        # T053: Skip aggregated component state topics with JSON - publish only RAW data
        # instead of complex JSON payloads. All state information is available through
        # fine-grained subtopics below (e.g., heater/temperature, heater/state, etc.)
        
        # Now publish fine-grained subtopics with simple RAW payloads (no JSON)
        components = snapshot.get("components", {})
        
        # DEBUG: Log what components we have
        logger.debug(f"Publishing snapshot with components: {list(components.keys())}")
        if "pumps" in components:
            pumps_list = components.get("pumps")
            logger.debug(f"Pumps in snapshot: {len(pumps_list) if isinstance(pumps_list, list) else 'NOT A LIST'} items")
        if "lights" in components:
            lights_list = components.get("lights")
            logger.debug(f"Lights in snapshot: {len(lights_list) if isinstance(lights_list, list) else 'NOT A LIST'} items")

    # Heater: simple state and temperature topics, plus one last_updated topic
        # Following T052: Separate read topics (current API values) from write topics
        heater = components.get("heater")
        if isinstance(heater, dict):
            # state as plain string (read-only, current API value)
            messages.append(MQTTMessage(
                topic=f"{base_topic}/heater/state",
                payload=str(heater.get("state", "unknown")),
                qos=1,
                retain=True
            ))
            # temperature as plain numeric or string (read-only, current API value)
            if heater.get("temperature") is not None:
                messages.append(MQTTMessage(
                    topic=f"{base_topic}/heater/temperature",
                    payload=str(heater.get("temperature")),
                    qos=1,
                    retain=True
                ))
            # target_temperature: current API value (read)
            if heater.get("target_temperature") is not None:
                messages.append(MQTTMessage(
                    topic=f"{base_topic}/heater/target_temperature",
                    payload=str(heater.get("target_temperature")),
                    qos=1,
                    retain=True
                ))
            # mode: current API value (read)
            if heater.get("mode") is not None:
                messages.append(MQTTMessage(
                    topic=f"{base_topic}/heater/mode",
                    payload=str(heater.get("mode")),
                    qos=1,
                    retain=True
                ))
            # single top-level timestamp for heater
            messages.append(MQTTMessage(
                topic=f"{base_topic}/heater/last_updated",
                payload=str(timestamp),
                qos=1,
                retain=True
            ))
            
            # T052: Publish heater meta topic documenting write topics for OpenHAB
            # These document where OpenHAB should write commands
            try:
                meta = {
                    "supports": {
                        "target_temperature": heater.get("target_temperature") is not None,
                        "mode": heater.get("mode") is not None,
                    },
                    # T052: publish the recommended command topics for heater
                    "target_temperature_writetopic": f"{base_topic}/heater/target_temperature_writetopic",
                    "mode_writetopic": f"{base_topic}/heater/mode_writetopic",
                    "last_updated": timestamp,
                }
                topic_meta = f"{base_topic}/heater/meta"
                messages.append(MQTTMessage(
                    topic=topic_meta,
                    payload=json.dumps(meta),
                    qos=1,
                    retain=True
                ))
                logger.info("created-heater-meta", extra={"topic": topic_meta, "spa_id": spa_id})
            except Exception:
                # don't let a meta serialization error break snapshot publish
                pass

        # Spa: overall state and temperature readings + one last_updated
        spa = components.get("spa")
        if isinstance(spa, dict):
            messages.append(MQTTMessage(
                topic=f"{base_topic}/spa/state",
                payload=str(spa.get("state", "unknown")),
                qos=1,
                retain=True
            ))
            if spa.get("water_temperature") is not None:
                messages.append(MQTTMessage(
                    topic=f"{base_topic}/spa/water_temperature",
                    payload=str(spa.get("water_temperature")),
                    qos=1,
                    retain=True
                ))
            if spa.get("air_temperature") is not None:
                messages.append(MQTTMessage(
                    topic=f"{base_topic}/spa/air_temperature",
                    payload=str(spa.get("air_temperature")),
                    qos=1,
                    retain=True
                ))
            messages.append(MQTTMessage(
                topic=f"{base_topic}/spa/last_updated",
                payload=str(timestamp),
                qos=1,
                retain=True
            ))

        # Pumps: publish aggregated list (already done) and per-pump simple topics; one pumps/last_updated
        pumps = components.get("pumps")
        if isinstance(pumps, list):
            for pump in pumps:
                pid = pump.get("id") or pump.get("pumpId") or "unknown"
                # state -> plain
                messages.append(MQTTMessage(
                    topic=f"{base_topic}/pumps/{pid}/state",
                    payload=str(pump.get("state", "unknown")),
                    qos=1,
                    retain=True
                ))
                # id and type as separate simple topics for easy discovery
                messages.append(MQTTMessage(
                    topic=f"{base_topic}/pumps/{pid}/id",
                    payload=str(pid),
                    qos=1,
                    retain=True
                ))
                messages.append(MQTTMessage(
                    topic=f"{base_topic}/pumps/{pid}/type",
                    payload=str(pump.get("type", "unknown")),
                    qos=1,
                    retain=True
                ))
                # speed -> plain
                if pump.get("speed") is not None:
                    messages.append(MQTTMessage(
                        topic=f"{base_topic}/pumps/{pid}/speed",
                        payload=str(pump.get("speed")),
                        qos=1,
                        retain=True
                    ))
                # last_updated per pump
                messages.append(MQTTMessage(
                    topic=f"{base_topic}/pumps/{pid}/last_updated",
                    payload=str(timestamp),
                    qos=1,
                    retain=True
                ))
                # per-pump retained meta topic describing the pump and where to
                # send commands for it. This includes a state_writetopic so MQTT
                # clients can discover the proper control topic for the pump.
                # T052: Using _writetopic convention instead of set_ prefix
                try:
                    meta = {
                        "id": pid,
                        "type": pump.get("type"),
                        "supports": {
                            "speed": pump.get("speed") is not None,
                        },
                        # T052: publish the recommended command topic for this pump
                        "state_writetopic": f"{base_topic}/pumps/{pid}/state_writetopic",
                        "last_updated": timestamp,
                    }
                    topic_meta = f"{base_topic}/pumps/{pid}/meta"
                    messages.append(MQTTMessage(
                        topic=topic_meta,
                        payload=json.dumps(meta),
                        qos=1,
                        retain=True
                    ))
                    # Info-level log so operators can see meta topics even when
                    # logger is set to INFO (debug logs are more verbose).
                    logger.info("created-pump-meta", extra={"topic": topic_meta, "spa_id": spa_id, "pump_id": pid})
                except Exception:
                    # don't let a meta serialization error break snapshot publish
                    pass
            # pumps top-level timestamp
            messages.append(MQTTMessage(
                topic=f"{base_topic}/pumps/last_updated",
                payload=str(timestamp),
                qos=1,
                retain=True
            ))

            # No legacy (non-spa) per-pump topics are published anymore; prefer
            # spa-scoped topics under <base_topic>/<spa_id>/pumps/...

        # Lights: per-zone topics for state, color and brightness; single lights/last_updated
        # T052: Publish read topics (current API values) and document write topics in meta
        # T053: Include mode for special light modes (LowSpeedWheel, ColorWheel, etc.)
        lights = components.get("lights")
        if isinstance(lights, list):
            for light in lights:
                lid = light.get("id") or f"zone_{light.get('zone', 'unknown')}"
                # Read topic: current state from API (on/off)
                messages.append(MQTTMessage(
                    topic=f"{base_topic}/lights/{lid}/state",
                    payload=str(light.get("state", "unknown")),
                    qos=1,
                    retain=True
                ))
                # Read topic: current mode from API (OFF, WHITE, PURPLE, LowSpeedWheel, ColorWheel, etc.)
                if light.get("mode") is not None:
                    messages.append(MQTTMessage(
                        topic=f"{base_topic}/lights/{lid}/mode",
                        payload=str(light.get("mode")),
                        qos=1,
                        retain=True
                    ))
                # Read topic: current color from API
                if light.get("color") is not None:
                    messages.append(MQTTMessage(
                        topic=f"{base_topic}/lights/{lid}/color",
                        payload=str(light.get("color")),
                        qos=1,
                        retain=True
                    ))
                # Read topic: current brightness from API
                if light.get("brightness") is not None:
                    messages.append(MQTTMessage(
                        topic=f"{base_topic}/lights/{lid}/brightness",
                        payload=str(light.get("brightness")),
                        qos=1,
                        retain=True
                    ))
                # Per-light timestamp
                messages.append(MQTTMessage(
                    topic=f"{base_topic}/lights/{lid}/last_updated",
                    payload=str(timestamp),
                    qos=1,
                    retain=True
                ))
                
                # T052: per-light meta topic documenting write topics for OpenHAB
                try:
                    # Load detected_modes from YAML if available
                    detected_modes = self._load_detected_modes_for_light(spa_id, lid)
                    
                    meta = {
                        "id": lid,
                        "zone": light.get("zone"),
                        "supports": {
                            "state": True,
                            "mode": light.get("mode") is not None,
                            "color": light.get("color") is not None,
                            "brightness": light.get("brightness") is not None,
                        },
                        # T052: publish the recommended command topics for this light
                        "state_writetopic": f"{base_topic}/lights/{lid}/state_writetopic",
                        "mode_writetopic": f"{base_topic}/lights/{lid}/mode_writetopic" if light.get("mode") is not None else None,
                        "color_writetopic": f"{base_topic}/lights/{lid}/color_writetopic" if light.get("color") is not None else None,
                        "brightness_writetopic": f"{base_topic}/lights/{lid}/brightness_writetopic" if light.get("brightness") is not None else None,
                        "detected_modes": detected_modes,  # Add detected modes from YAML
                        "last_updated": timestamp,
                    }
                    topic_meta = f"{base_topic}/lights/{lid}/meta"
                    messages.append(MQTTMessage(
                        topic=topic_meta,
                        payload=json.dumps(meta),
                        qos=1,
                        retain=True
                    ))
                    logger.info("created-light-meta", extra={"topic": topic_meta, "spa_id": spa_id, "light_id": lid})
                except Exception as e:
                    # don't let a meta serialization error break snapshot publish
                    logger.warning(f"Error creating light meta for {lid}: {e}")
                    pass
                    
            messages.append(MQTTMessage(
                topic=f"{base_topic}/lights/last_updated",
                payload=str(timestamp),
                qos=1,
                retain=True
            ))

            # No legacy (non-spa) per-light topics are published anymore; prefer
            # spa-scoped topics under <base_topic>/<spa_id>/lights/...

        return messages

    def publish_messages(self, messages: List[MQTTMessage]) -> None:
        """Publish a list of MQTT messages.

        Args:
            messages: List of messages to publish
        """
        logger = logging.getLogger(__name__)

        for message in messages:
            try:
                # Log intent before publish to make it visible in logs even if the
                # broker drops the connection immediately after.
                try:
                    payload_len = len(message.payload) if message.payload is not None else 0
                except Exception:
                    payload_len = None

                # Also emit an INFO log so retained/meta messages and normal
                # publishes are visible at INFO level (not only DEBUG).
                logger.info("publishing-mqtt-message", extra={
                    "topic": message.topic,
                    "payload_len": payload_len,
                    "qos": message.qos,
                    "retain": message.retain,
                })

                self.mqtt_client.publish(
                    topic=message.topic,
                    payload=message.payload,
                    qos=message.qos,
                    retain=message.retain
                )
            except Exception as e:
                logger.warning("mqtt-publish-error", exc_info=e, extra={"topic": getattr(message, 'topic', None)})

    def publish_capability_meta(self, spa_id: str, capability_profile: dict[str, Any]) -> MQTTMessage:
        """Backward-compatible single-message publisher for capability meta.

        This method keeps the old behaviour for callers/tests that expect one
        aggregated message. New code should prefer
        `publish_capability_meta_entries` which returns separate messages per
        capability entry.
        """
        # keep old-style single message for compatibility
        base_topic = self.config.mqtt.base_topic
        if spa_id:
            topic = f"{base_topic}/{spa_id}/spa/capability/meta"
        else:
            topic = f"{base_topic}/spa/{spa_id}/capability/meta"

        payload = json.dumps(capability_profile)
        return MQTTMessage(topic=topic, payload=payload, qos=1, retain=True)

    def publish_capability_meta_entries(self, spa_id: str, capability_profile: dict[str, Any]) -> List[MQTTMessage]:
        """Publish capability meta as separate MQTT messages per entry.

        Args:
            spa_id: ID of the spa
            capability_profile: Capability profile dict

        Returns:
            List of MQTTMessage, one per top-level capability_profile entry
        """
        messages: List[MQTTMessage] = []
        base_topic = self.config.mqtt.base_topic
        if spa_id:
            base = f"{base_topic}/{spa_id}/spa/capability"
        else:
            base = f"{base_topic}/spa/capability"

        for key, value in capability_profile.items():
            # For scalar values (str/int/float/bool/None) publish the raw scalar
            # as the payload (no {"value": ...} wrapper). For complex objects
            # publish a JSON serialization.
            if isinstance(value, (str, int, float, bool)) or value is None:
                payload = "" if value is None else str(value)
            else:
                payload = json.dumps(value)

            topic = f"{base}/{key}"
            messages.append(MQTTMessage(topic=topic, payload=payload, qos=1, retain=True))

        return messages

    def publish_version_meta(self) -> List[MQTTMessage]:
        """Publish global version metadata.
        
        Publishes version information to global meta topics:
        - {base_topic}/meta/smarttub-mqtt: smarttub-mqtt version only
        - {base_topic}/meta/python-smarttub: python-smarttub version only
        
        Returns:
            List of MQTT messages with version information
        """
        from src.core.version import get_version_info
        version_info = get_version_info()
        
        messages = []
        
        # Publish smarttub-mqtt version to meta/smarttub-mqtt
        topic_smarttub_mqtt = f"{self.config.mqtt.base_topic}/meta/smarttub-mqtt"
        payload_smarttub_mqtt = version_info["smarttub_mqtt"]
        messages.append(MQTTMessage(topic=topic_smarttub_mqtt, payload=payload_smarttub_mqtt, qos=1, retain=True))
        
        # Publish python-smarttub version to meta/python-smarttub
        topic_python_smarttub = f"{self.config.mqtt.base_topic}/meta/python-smarttub"
        payload_python_smarttub = version_info["python_smarttub"]
        messages.append(MQTTMessage(topic=topic_python_smarttub, payload=payload_python_smarttub, qos=1, retain=True))
        
        return messages

    def _load_detected_modes_for_light(self, spa_id: str, light_id: str) -> List[str]:
        """Load detected_modes from discovered_items.yaml for a specific light.
        
        Args:
            spa_id: The spa identifier
            light_id: The light identifier (e.g., "zone_1")
            
        Returns:
            List of detected modes, empty if none found
        """
        try:
            # Try multiple paths where the YAML might be
            yaml_paths = [
                Path("/config/discovered_items.yaml"),
                Path("config/discovered_items.yaml"),
                Path("discovered_items.yaml")
            ]
            
            yaml_path = None
            for path in yaml_paths:
                if path.exists():
                    yaml_path = path
                    logger.debug(f"Found YAML at {yaml_path}")
                    break
            
            if not yaml_path:
                logger.debug(f"No discovered_items.yaml found for {spa_id}/{light_id}")
                return []
            
            # Load YAML file
            with open(yaml_path, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data or 'discovered_items' not in data:
                logger.debug(f"No discovered_items key in YAML for {spa_id}/{light_id}")
                return []
            
            # Get spa data
            spa_data = data['discovered_items'].get(spa_id)
            if not spa_data:
                logger.debug(f"No spa data found for {spa_id} in YAML")
                return []
            
            # Get lights data
            lights = spa_data.get('lights', [])
            if not lights:
                logger.debug(f"No lights found for {spa_id} in YAML")
                return []
            
            # Find the specific light by ID
            for light in lights:
                if light.get('id') == light_id:
                    detected = light.get('detected_modes', [])
                    logger.debug(f"Found detected_modes for {spa_id}/{light_id}: {detected}")
                    return detected
            
            logger.debug(f"Light {light_id} not found for {spa_id} in YAML")
            return []
            
        except Exception as e:
            logger.debug(f"Error loading detected_modes from YAML for {spa_id}/{light_id}: {e}")
            return []

    def publish_discovery_status(self, state: Any) -> List[MQTTMessage]:
        """
        Publish discovery status to MQTT.
        
        Topics:
        - {base_topic}/discovery/status: Current discovery status (JSON)
        
        Args:
            state: DiscoveryState object
            
        Returns:
            List of MQTT messages to publish
        """
        messages = []
        base_topic = self.config.mqtt.base_topic
        
        # Build status payload
        status_data = {
            "status": state.status.value,
            "mode": state.mode.value if state.mode else None,
            "started_at": state.started_at.isoformat() if state.started_at else None,
            "completed_at": state.completed_at.isoformat() if state.completed_at else None,
            "progress": {
                "percentage": state.progress.percentage,
                "current_spa": state.progress.current_spa,
                "current_light": state.progress.current_light,
                "lights_total": state.progress.lights_total,
                "lights_tested": state.progress.lights_tested,
                "modes_total": state.progress.modes_total,
                "modes_tested": state.progress.modes_tested,
            },
            "error": state.error,
        }
        
        # Status topic (not retained - current state)
        topic_status = f"{base_topic}/discovery/status"
        payload_status = json.dumps(status_data, indent=2)
        messages.append(MQTTMessage(
            topic=topic_status,
            payload=payload_status,
            qos=1,
            retain=False  # Not retained - status changes frequently
        ))
        
        # If completed, publish results (retained)
        if state.status.value == "completed" and state.results:
            result_data = {
                "completed_at": state.completed_at.isoformat() if state.completed_at else None,
                "yaml_path": state.results.yaml_path,
                "total_lights": state.results.total_lights,
                "total_modes_detected": state.results.total_modes_detected,
                "spas": state.results.spas,
            }
            
            topic_result = f"{base_topic}/discovery/result"
            payload_result = json.dumps(result_data, indent=2)
            messages.append(MQTTMessage(
                topic=topic_result,
                payload=payload_result,
                qos=1,
                retain=True  # Retained - last discovery result
            ))
        
        logger.debug(f"Publishing discovery status: {state.status.value}")
        return messages

    def get_discovery_control_topic(self) -> str:
        """
        Get the MQTT topic for discovery control commands.
        
        Returns:
            Control topic path
        """
        return f"{self.config.mqtt.base_topic}/discovery/control"


# Convenience function for backward compatibility with tests
def publish_state_snapshot(config: AppConfig, snapshot: dict[str, Any]) -> List[MQTTMessage]:
    """Convert a state snapshot into MQTT messages for publishing.

    This is a convenience function that creates a temporary mapper instance.
    In production code, use MQTTTopicMapper class directly.

    Args:
        config: Application configuration
        snapshot: State snapshot with timestamp and components

    Returns:
        List of MQTT messages to publish
    """
    # Create a dummy client for this function (not used in message creation)
    class DummyClient:
        pass

    mapper = MQTTTopicMapper(config, DummyClient())
    return mapper.publish_state_snapshot(snapshot)