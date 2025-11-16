"""
YAML Fallback Publisher.

Publishes light metadata with detected_modes from discovered_items.yaml
at startup, before the first live API call.
"""

import logging
import yaml
from pathlib import Path
from typing import List

from src.mqtt.topic_mapper import MQTTTopicMapper

logger = logging.getLogger(__name__)


class YAMLFallbackPublisher:
    """
    Publishes light metadata from YAML at startup.

    This ensures that detected_modes are available immediately,
    even before the first live API poll.

    Usage:
        publisher = YAMLFallbackPublisher(
            topic_mapper=topic_mapper
        )

        # Publish at startup
        await publisher.publish_from_yaml()
    """

    def __init__(
        self,
        topic_mapper: MQTTTopicMapper,
    ):
        """
        Initialize YAML fallback publisher.

        Args:
            topic_mapper: MQTT topic mapper for publishing
        """
        self.topic_mapper = topic_mapper

        logger.info("YAMLFallbackPublisher initialized")

    async def publish_from_yaml(
        self, yaml_path: Path = Path("/config/discovered_items.yaml")
    ) -> bool:
        """
        Load discovered_items.yaml and publish light metadata.

        Args:
            yaml_path: Path to discovered_items.yaml

        Returns:
            True if published successfully, False otherwise
        """
        try:
            # Check if YAML exists
            if not yaml_path.exists():
                logger.warning(
                    f"YAML file not found: {yaml_path} - skipping fallback publishing"
                )
                return False

            # Load YAML
            logger.info(f"Loading discovered items from {yaml_path}")
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)

            if not data or "discovered_items" not in data:
                logger.warning(
                    f"Invalid YAML structure in {yaml_path} - missing 'discovered_items' key"
                )
                return False

            discovered_items = data["discovered_items"]

            # Track statistics
            total_spas = 0
            total_lights = 0
            total_modes = 0

            # Process each spa
            for spa_id, spa_data in discovered_items.items():
                total_spas += 1

                lights = spa_data.get("lights", [])

                # Process each light
                for light in lights:
                    total_lights += 1

                    light_id = light.get("id")
                    detected_modes = light.get("detected_modes", [])

                    if not light_id:
                        logger.warning(f"Light without ID in spa {spa_id}, skipping")
                        continue

                    total_modes += len(detected_modes)

                    # Publish light meta with detected_modes
                    await self._publish_light_meta(
                        spa_id=spa_id, light_id=light_id, detected_modes=detected_modes
                    )

            logger.info(
                f"YAML fallback publishing complete: "
                f"{total_spas} spas, {total_lights} lights, {total_modes} modes"
            )

            return True

        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error: {e}")
            return False

        except Exception as e:
            logger.error(f"Error publishing from YAML: {e}", exc_info=True)
            return False

    async def _publish_light_meta(
        self, spa_id: str, light_id: str, detected_modes: List[str]
    ):
        """
        Publish light metadata to MQTT.

        Args:
            spa_id: Spa identifier
            light_id: Light identifier (e.g., "zone_1")
            detected_modes: List of detected light modes
        """
        try:
            # Build topic
            base_topic = self.topic_mapper.config.mqtt.base_topic
            topic = f"{base_topic}/{spa_id}/lights/{light_id}/meta/detected_modes"

            # Build payload (comma-separated list)
            payload = ",".join(detected_modes) if detected_modes else ""

            # Publish via topic mapper's MQTT client
            self.topic_mapper.mqtt_client.publish(
                topic=topic, payload=payload, qos=1, retain=True
            )

            logger.debug(
                f"Published light meta: {spa_id}/{light_id} - "
                f"{len(detected_modes)} modes"
            )

        except Exception as e:
            logger.error(
                f"Error publishing light meta for {spa_id}/{light_id}: {e}",
                exc_info=True,
            )
