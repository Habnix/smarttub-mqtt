"""
Discovery Coordinator.

High-level facade for discovery functionality.
Coordinates State Manager, Runner, and MQTT publishing.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Optional

from src.core.background_discovery import BackgroundDiscoveryRunner
from src.core.config_loader import AppConfig
from src.core.discovery_state import (
    DiscoveryMode,
    DiscoveryState,
    DiscoveryStateManager,
)
from src.core.light_mode_catalog import light_mode_catalog
from src.core.smarttub_client import SmartTubClient

logger = logging.getLogger(__name__)


class DiscoveryCoordinator:
    """
    High-level coordinator for discovery operations.

    Provides a simple API for starting, stopping, and monitoring discovery.
    Handles MQTT publishing of status updates and coordinates all components.

    This is the main interface that WebUI and MQTT handlers should use.

    Usage:
        coordinator = DiscoveryCoordinator(
            smarttub_client=client,
            config=config
        )

        # Start discovery
        result = await coordinator.start_discovery(mode="quick")

        # Get status
        status = await coordinator.get_status()

        # Stop discovery
        await coordinator.stop_discovery()
    """

    _instance: Optional["DiscoveryCoordinator"] = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        """Singleton pattern - only one coordinator instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        smarttub_client: SmartTubClient,
        config: AppConfig,
    ):
        """
        Initialize discovery coordinator.

        Args:
            smarttub_client: SmartTub API client
            config: Application configuration
        """
        # Only initialize once
        if hasattr(self, "_initialized"):
            return

        self.smarttub_client = smarttub_client
        self.config = config

        # Create components
        self.state_manager = DiscoveryStateManager()
        self.runner = BackgroundDiscoveryRunner(
            state_manager=self.state_manager,
            smarttub_client=smarttub_client,
            config=config,
        )

        # MQTT publisher (will be set later)
        self._mqtt_publisher: Callable[[DiscoveryState], Awaitable[None]] | None = None
        self._persisted_state_loaded = False

        # Subscribe to state changes for auto-publishing
        self.state_manager.subscribe(self._on_state_change)

        self._initialized = True

        logger.info("DiscoveryCoordinator initialized")

    async def start_discovery(self, mode: str = "quick") -> dict[str, Any]:
        """
        Start discovery process.

        Args:
            mode: Discovery mode ("full", "quick", or "yaml_only")

        Returns:
            Result dict with success/error and details
        """
        async with self._lock:
            try:
                # Convert mode string to enum
                try:
                    discovery_mode = DiscoveryMode(mode)
                except ValueError:
                    return {
                        "success": False,
                        "error": f"Invalid mode: {mode}. Use 'full', 'quick', or 'yaml_only'",
                    }

                # Check if already running
                if self.runner.is_running():
                    return {"success": False, "error": "Discovery already running"}

                # Start discovery
                result = await self.runner.start_discovery(discovery_mode)

                logger.info(f"Discovery started via coordinator: mode={mode}")

                return result

            except Exception as e:
                logger.exception("Failed to start discovery")
                return {"success": False, "error": str(e)}

    async def stop_discovery(self) -> dict[str, Any]:
        """
        Stop running discovery process.

        Returns:
            Result dict with success/error and details
        """
        async with self._lock:
            try:
                # Check if running
                if not self.runner.is_running():
                    return {"success": False, "error": "No discovery running"}

                # Stop discovery
                result = await self.runner.stop_discovery()

                logger.info("Discovery stopped via coordinator")

                return result

            except Exception as e:
                logger.exception("Failed to stop discovery")
                return {"success": False, "error": str(e)}

    async def get_status(self) -> dict[str, Any]:
        """
        Get current discovery status.

        Returns:
            Status dict with state information
        """
        try:
            await self._ensure_persisted_state_loaded()
            state = await self.state_manager.get_state()

            return {
                "success": True,
                "mode_catalog": light_mode_catalog(),
                "status": state.status.value,
                "mode": state.mode.value if state.mode else None,
                "is_running": self.runner.is_running(),
                "started_at": state.started_at.isoformat()
                if state.started_at
                else None,
                "completed_at": state.completed_at.isoformat()
                if state.completed_at
                else None,
                "progress": state.progress.to_dict(),
                "error": state.error,
                "results": state.results.to_dict() if state.results else None,
            }

        except Exception as e:
            logger.exception("Failed to get status")
            return {"success": False, "error": str(e)}

    async def get_results(self) -> dict[str, Any]:
        """
        Get discovery results (if available).

        Returns:
            Results dict or error
        """
        try:
            await self._ensure_persisted_state_loaded()
            state = await self.state_manager.get_state()

            if state.results is None:
                return {
                    "success": False,
                    "error": "No results available. Run discovery first.",
                }

            return {"success": True, "results": state.results.to_dict()}

        except Exception as e:
            logger.exception("Failed to get results")
            return {"success": False, "error": str(e)}

    async def _ensure_persisted_state_loaded(self) -> None:
        """Restore the last completed run from YAML once after startup."""
        if self._persisted_state_loaded:
            return
        self._persisted_state_loaded = True

        current_state = await self.state_manager.get_state()
        if current_state.status.value != "idle":
            return

        persisted = await self.runner.result_store.load_last_run_async()
        if not persisted:
            return

        try:
            mode = DiscoveryMode(str(persisted["mode"]))
            started_at = datetime.fromisoformat(str(persisted["started_at"]))
            completed_at = datetime.fromisoformat(str(persisted["completed_at"]))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Ignoring invalid persisted discovery metadata: %s", exc)
            return

        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=UTC)

        await self.state_manager.update_state(
            {
                "status": "completed",
                "mode": mode,
                "started_at": started_at,
                "completed_at": completed_at,
                "results": persisted["results"],
                "error": None,
            }
        )
        logger.info(
            "Restored persisted discovery run from %s", self.runner.result_store.path
        )

    def set_mqtt_publisher(
        self, publisher: Callable[[DiscoveryState], Awaitable[None]]
    ) -> None:
        """
        Set MQTT publisher callback.

        This will be called automatically when state changes.

        Args:
            publisher: Async function to publish state to MQTT
                Signature: async def publisher(state: DiscoveryState)
        """
        self._mqtt_publisher = publisher
        logger.debug("MQTT publisher registered")

    async def publish_status_to_mqtt(self) -> None:
        """
        Manually trigger MQTT status publication.

        Publishes current state to MQTT topics.
        """
        if self._mqtt_publisher is None:
            logger.warning("No MQTT publisher registered, cannot publish status")
            return

        try:
            state = await self.state_manager.get_state()
            await self._mqtt_publisher(state)
            logger.debug("Published discovery status to MQTT")

        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to publish to MQTT: {e}")

    async def _on_state_change(self, state: DiscoveryState) -> None:
        """
        Observer callback for state changes.

        Automatically publishes to MQTT when state changes.

        Args:
            state: Updated discovery state
        """
        logger.debug(f"Discovery state changed: {state.status.value}")

        # Auto-publish to MQTT
        if self._mqtt_publisher is not None:
            try:
                await self._mqtt_publisher(state)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Failed to auto-publish to MQTT: {e}")

    def is_running(self) -> bool:
        """
        Check if discovery is currently running.

        Returns:
            True if discovery is active
        """
        return self.runner.is_running()

    async def reset_state(self) -> dict[str, Any]:
        """
        Reset discovery state to idle.

        Can only be done when discovery is not running.

        Returns:
            Result dict
        """
        async with self._lock:
            if self.runner.is_running():
                return {
                    "success": False,
                    "error": "Cannot reset while discovery is running",
                }

            try:
                await self.state_manager.reset()
                logger.info("Discovery state reset")

                return {"success": True, "message": "State reset to idle"}

            except Exception as e:
                logger.exception("Failed to reset state")
                return {"success": False, "error": str(e)}

    @classmethod
    def get_instance(cls) -> Optional["DiscoveryCoordinator"]:
        """
        Get singleton instance (if exists).

        Returns:
            Coordinator instance or None
        """
        return cls._instance

    @classmethod
    async def shutdown(cls):
        """
        Shutdown coordinator and cleanup resources.

        Should be called on application shutdown.
        """
        if cls._instance is None:
            return

        logger.info("Shutting down DiscoveryCoordinator...")

        # Stop discovery if running
        if cls._instance.runner.is_running():
            await cls._instance.stop_discovery()

        # Clear instance
        cls._instance = None

        logger.info("DiscoveryCoordinator shutdown complete")
