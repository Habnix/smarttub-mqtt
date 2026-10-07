"""
Background Discovery Runner.

Executes discovery process as async background task with progress tracking
and graceful shutdown support.
"""

import asyncio
import logging
from datetime import UTC, datetime
from functools import partial
from typing import Any

from src.core.config_loader import AppConfig
from src.core.discovery_recovery import DiscoveryRecoveryJournal
from src.core.discovery_result_store import DiscoveryResultStore
from src.core.discovery_state import (
    DiscoveryMode,
    DiscoveryResults,
    DiscoveryStateManager,
    DiscoveryStatus,
)
from src.core.light_discovery_engine import LightDiscoveryEngine
from src.core.light_mode_catalog import is_mode_detected, light_modes_for_discovery
from src.core.smarttub_client import SmartTubClient
from src.core.smarttub_gateway import SmartTubGateway

logger = logging.getLogger(__name__)


class DiscoveryError(RuntimeError):
    """Base error for expected discovery failures."""


class BackgroundDiscoveryRunner:
    """
    Background discovery task runner.

    Executes discovery in the background without blocking main application.
    Supports graceful stop and real-time progress updates.

    Usage:
        runner = BackgroundDiscoveryRunner(
            state_manager=state_manager,
            smarttub_client=client,
            config=config
        )

        # Start discovery
        await runner.start_discovery(mode="quick")

        # Check if running
        is_running = runner.is_running()

        # Stop discovery
        await runner.stop_discovery()
    """

    def __init__(
        self,
        state_manager: DiscoveryStateManager,
        smarttub_client: SmartTubClient,
        config: AppConfig,
        *,
        recovery_journal: DiscoveryRecoveryJournal | None = None,
    ):
        """
        Initialize background discovery runner.

        Args:
            state_manager: State manager for progress tracking
            smarttub_client: SmartTub API client
            config: Application configuration
        """
        self.state_manager = state_manager
        self.smarttub_client = smarttub_client
        self.config = config
        self.gateway = getattr(smarttub_client, "gateway", SmartTubGateway())

        self._task: asyncio.Task[Any] | None = None
        self._stop_event = asyncio.Event()
        self._start_lock = asyncio.Lock()  # Prevent concurrent starts

        # Discovery configuration
        self.result_store = DiscoveryResultStore()
        self.recovery_journal = recovery_journal or DiscoveryRecoveryJournal()
        self.discovery_engine = LightDiscoveryEngine(
            config,
            gateway=self.gateway,
            recovery_journal=self.recovery_journal,
        )

        # Mode-specific test configurations
        self.mode_configs = {
            DiscoveryMode.FULL: {
                "test_modes": True,
                "catalogue_mode": "full",
                "wait_time": 8,
            },
            DiscoveryMode.QUICK: {
                "test_modes": True,
                "catalogue_mode": "quick",
                "wait_time": 8,
            },
            DiscoveryMode.YAML_ONLY: {
                "test_modes": False,
                "catalogue_mode": "yaml_only",
                "wait_time": 0,
            },
        }

        logger.debug("BackgroundDiscoveryRunner initialized")

    def is_running(self) -> bool:
        """
        Check if discovery is currently running.

        Returns:
            True if discovery task is active
        """
        return self._task is not None and not self._task.done()

    async def start_discovery(
        self, mode: DiscoveryMode = DiscoveryMode.QUICK
    ) -> dict[str, Any]:
        """
        Start background discovery process.

        Args:
            mode: Discovery mode (full/quick/yaml_only)

        Returns:
            Status dict with success/error
        """
        # Use lock to prevent race conditions
        async with self._start_lock:
            # Check if already running
            if self.is_running():
                logger.warning("Discovery already running, cannot start new task")
                return {
                    "success": False,
                    "error": "Discovery already running",
                }

            try:
                await self._recover_pending_lights()
            except Exception as exc:
                logger.exception("Discovery recovery must complete before a new run")
                return {
                    "success": False,
                    "error": (
                        "A previous discovery state could not be restored; "
                        "manual recovery is required"
                    ),
                    "details": type(exc).__name__,
                }

            # Reset stop event
            self._stop_event.clear()

            # Update state to running
            await self.state_manager.update_state(
                {
                    "status": DiscoveryStatus.RUNNING,
                    "mode": mode,
                    "started_at": datetime.now(UTC),
                    "error": None,
                }
            )

        # Start background task
        self._task = asyncio.create_task(self._run_discovery_loop(mode))

        logger.info(f"Discovery started in {mode.value} mode")

        return {
            "success": True,
            "mode": mode.value,
            "started_at": datetime.now(UTC).isoformat(),
        }

    async def stop_discovery(self) -> dict[str, Any]:
        """
        Stop running discovery process gracefully.

        Returns:
            Status dict with success/error
        """
        if not self.is_running():
            logger.warning("No discovery running, nothing to stop")
            return {
                "success": False,
                "error": "No discovery running",
            }

        logger.info("Stopping discovery...")

        # Signal stop
        self._stop_event.set()

        # Wait for task to complete (with timeout)
        task = self._task
        if task is None:
            return {"success": False, "error": "No discovery running"}

        try:
            await asyncio.wait_for(task, timeout=10.0)
        except TimeoutError:
            logger.warning("Discovery task did not stop gracefully, cancelling")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Update state
        await self.state_manager.update_state(
            {
                "status": DiscoveryStatus.IDLE,
                "error": "Stopped by user",
            }
        )

        logger.info("Discovery stopped")

        return {
            "success": True,
            "stopped_at": datetime.now(UTC).isoformat(),
        }

    async def _run_discovery_loop(self, mode: DiscoveryMode):
        """
        Main discovery loop (runs in background task).

        Args:
            mode: Discovery mode
        """
        try:
            logger.info(f"Starting discovery loop in {mode.value} mode")
            started_at = datetime.now(UTC)

            # Get mode configuration
            mode_config: dict[str, Any] = self.mode_configs[mode]

            # Load spas from client
            spas = self.smarttub_client.spas

            if not spas:
                raise DiscoveryError("No spas found in account")

            logger.info(f"Found {len(spas)} spa(s)")

            # Process each spa
            results: dict[str, Any] = {"spas": {}}

            for spa in spas:
                spa_id = spa.id
                logger.info(f"Processing spa {spa_id}")

                # Check stop signal
                if self._stop_event.is_set():
                    logger.info("Stop signal received, aborting discovery")
                    return

                # Update progress
                await self.state_manager.update_progress(current_spa=spa_id)

                # Get lights for this spa
                lights = await spa.get_lights()

                if not lights:
                    logger.warning(f"No lights found for spa {spa_id}")
                    continue

                logger.info(f"Found {len(lights)} light(s) for spa {spa_id}")

                # Initialize spa results
                spa_results: dict[str, Any] = {"spa_id": spa_id, "lights": []}

                # Calculate total modes to test
                if mode_config["test_modes"]:
                    modes_to_test = list(
                        light_modes_for_discovery(mode_config["catalogue_mode"])
                    )

                    total_modes = len(lights) * len(modes_to_test)
                else:
                    modes_to_test = []
                    total_modes = 0

                # Update progress with totals
                await self.state_manager.update_progress(
                    lights_total=len(lights),
                    modes_total=total_modes,
                    lights_tested=0,
                    modes_tested=0,
                )

                # Process each light
                for light_idx, light in enumerate(lights):
                    light_id = f"zone_{light.zone}"
                    logger.info(f"Processing light {light_id}")

                    # Check stop signal
                    if self._stop_event.is_set():
                        logger.info("Stop signal received, aborting discovery")
                        return

                    # Update current light
                    await self.state_manager.update_progress(current_light=light_id)

                    light_results = {
                        "id": light_id,
                        "zone": light.zone,
                        "detected_modes": [],
                        "mode_results": {},
                    }
                    # Test modes if enabled. The shared engine owns state capture,
                    # journalling and verified restoration around this callback.
                    if mode_config["test_modes"]:
                        stopped, restored = await self.discovery_engine.run_probe(
                            str(spa_id),
                            light,
                            partial(
                                self._probe_selected_modes,
                                light=light,
                                light_id=light_id,
                                modes=tuple(modes_to_test),
                                wait_time=mode_config["wait_time"],
                                light_results=light_results,
                            ),
                        )
                        light_results["state_restored"] = restored
                        if stopped:
                            return
                    else:
                        light_results["state_restored"] = None

                    # Add light to results
                    spa_results["lights"].append(light_results)

                    # Update lights tested
                    await self.state_manager.update_progress(
                        lights_tested=light_idx + 1
                    )

                # Add spa to results
                results["spas"][spa_id] = spa_results

            # Save results to YAML
            completed_at = datetime.now(UTC)
            total_lights = sum(len(s["lights"]) for s in results["spas"].values())
            total_modes_detected = sum(
                len(light["detected_modes"])
                for spa in results["spas"].values()
                for light in spa["lights"]
            )
            yaml_path = await self.result_store.save_light_modes_async(
                results,
                run_metadata={
                    "mode": mode.value,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "total_lights": total_lights,
                    "total_modes_detected": total_modes_detected,
                },
            )

            # Create discovery results
            discovery_results = DiscoveryResults(
                spas=results["spas"],
                yaml_path=str(yaml_path),
                total_lights=total_lights,
                total_modes_detected=total_modes_detected,
            )

            # Update state to completed
            await self.state_manager.update_state(
                {
                    "status": DiscoveryStatus.COMPLETED,
                    "completed_at": completed_at,
                    "results": discovery_results,
                }
            )

            logger.info(
                f"Discovery completed successfully: {discovery_results.total_lights} lights, "
                f"{discovery_results.total_modes_detected} modes detected"
            )

        except Exception as e:
            logger.exception("Discovery failed")

            # Update state to failed
            await self.state_manager.update_state(
                {
                    "status": DiscoveryStatus.FAILED,
                    "completed_at": datetime.now(UTC),
                    "error": str(e),
                }
            )

    @staticmethod
    def _capture_light_state(light: Any) -> dict[str, Any] | None:
        """Compatibility wrapper around the shared discovery engine."""
        return LightDiscoveryEngine.capture_light_state(light)

    async def _probe_selected_modes(
        self,
        *,
        light: Any,
        light_id: str,
        modes: tuple[str, ...],
        wait_time: int,
        light_results: dict[str, Any],
    ) -> bool:
        """Probe selected modes; return whether a stop was requested."""
        logger.info("Testing %s modes for %s", len(modes), light_id)
        for mode_name in modes:
            logger.info("Testing mode %s on %s", mode_name, light_id)
            if self._stop_event.is_set():
                logger.info("Stop signal received, aborting discovery")
                return True

            test_result = await self._test_light_mode(
                light=light,
                mode_name=mode_name,
                wait_time=wait_time,
            )
            light_results["mode_results"][mode_name] = test_result
            if is_mode_detected(test_result["status"]):
                light_results["detected_modes"].append(mode_name)

            state = await self.state_manager.get_state()
            await self.state_manager.update_progress(
                modes_tested=state.progress.modes_tested + 1
            )
        return False

    async def _restore_and_clear(
        self,
        spa_id: str,
        light: Any,
        original_state: dict[str, Any] | None,
    ) -> bool | None:
        """Compatibility wrapper around the shared discovery engine."""
        return await self.discovery_engine.restore_and_clear(
            spa_id, light, original_state
        )

    async def _recover_pending_lights(self) -> None:
        """Restore an interrupted discovery before accepting another run."""
        await self.discovery_engine.recover_pending(self.smarttub_client.spas)

    async def _restore_light_state_safely(
        self, light: Any, original_state: dict[str, Any] | None
    ) -> bool | None:
        """Compatibility wrapper around the shared discovery engine."""
        return await self.discovery_engine.restore_light_state(light, original_state)

    async def _test_light_mode(
        self, light: Any, mode_name: str, wait_time: int
    ) -> dict[str, Any]:
        """Compatibility wrapper around the shared discovery engine."""
        return await self.discovery_engine.test_mode(
            light, mode_name, wait_time=wait_time
        )
