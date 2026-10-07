"""Own the application lifecycle of the optional discovery integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass

from src.core.config_loader import AppConfig
from src.core.discovery_coordinator import DiscoveryCoordinator
from src.core.error_tracker import ErrorCategory, ErrorSeverity, ErrorTracker
from src.core.smarttub_client import SmartTubClient
from src.core.yaml_fallback import YAMLFallbackPublisher
from src.mqtt.broker_client import MQTTBrokerClient
from src.mqtt.discovery_handler import DiscoveryMQTTHandler
from src.mqtt.topic_mapper import MQTTTopicMapper

logger = logging.getLogger("smarttub.core.discovery")


@dataclass
class DiscoveryRuntime:
    """Create, start, and stop discovery services as one lifecycle unit."""

    config: AppConfig
    smarttub_client: SmartTubClient
    topic_mapper: MQTTTopicMapper
    broker: MQTTBrokerClient
    error_tracker: ErrorTracker
    event_loop: asyncio.AbstractEventLoop
    coordinator: DiscoveryCoordinator | None = None
    mqtt_handler: DiscoveryMQTTHandler | None = None

    async def start(self) -> None:
        """Initialize discovery services and apply the configured startup mode."""
        try:
            self.coordinator = DiscoveryCoordinator(
                smarttub_client=self.smarttub_client,
                config=self.config,
            )
            logger.info("Discovery Coordinator initialized")

            self.mqtt_handler = DiscoveryMQTTHandler(
                coordinator=self.coordinator,
                topic_mapper=self.topic_mapper,
                mqtt_client=self.broker,
                event_loop=self.event_loop,
            )
            await self.mqtt_handler.start()
            logger.info("Discovery MQTT Handler started")

            published = await YAMLFallbackPublisher(
                topic_mapper=self.topic_mapper,
                discovery_repository=getattr(
                    self.topic_mapper, "discovery_repository", None
                ),
            ).publish_from_yaml()
            if published:
                logger.info("YAML fallback publishing completed")

            discovery_mode = os.getenv("DISCOVERY_MODE", "off").lower()
            if discovery_mode in {"startup_quick", "startup_full", "startup_yaml"}:
                mode = discovery_mode.removeprefix("startup_")
                logger.info(
                    "Starting background discovery (%s mode) via DISCOVERY_MODE env var...",
                    mode,
                )
                await self.coordinator.start_discovery(mode=mode)
            else:
                logger.info(
                    "Discovery mode: %s (manual control via WebUI or MQTT)",
                    discovery_mode,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to initialize background discovery: %s", exc)
            self.error_tracker.track_error(
                category=ErrorCategory.DISCOVERY,
                message=f"Failed to initialize background discovery: {exc!s}",
                severity=ErrorSeverity.ERROR,
                error_code="DISCOVERY_INIT_FAILED",
            )

    async def stop(self) -> None:
        """Stop the MQTT handler and coordinator, if they were initialized."""
        if self.mqtt_handler is not None:
            with contextlib.suppress(Exception):
                await self.mqtt_handler.stop()
                logger.info("Discovery MQTT Handler stopped")

        if self.coordinator is not None:
            with contextlib.suppress(Exception):
                await DiscoveryCoordinator.shutdown()
                logger.info("Discovery Coordinator shutdown")
