"""
Background Discovery Runner.

Executes discovery process as async background task with progress tracking
and graceful shutdown support.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import yaml

from src.core.discovery_state import (
    DiscoveryStateManager,
    DiscoveryStatus,
    DiscoveryMode,
    DiscoveryResults,
)
from src.core.smarttub_client import SmartTubClient
from src.core.config_loader import AppConfig

logger = logging.getLogger(__name__)


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
        
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._start_lock = asyncio.Lock()  # Prevent concurrent starts
        
        # Discovery configuration
        self.yaml_path = Path("/config/discovered_items.yaml")
        
        # Mode-specific test configurations
        self.mode_configs = {
            DiscoveryMode.FULL: {
                "test_modes": True,
                "modes_to_test": "all",  # Test all 18 modes
                "wait_time": 20,  # Extra wait after timeout (SmartTub Cloud API is VERY slow)
            },
            DiscoveryMode.QUICK: {
                "test_modes": True,
                "modes_to_test": ["OFF", "ON", "PURPLE", "WHITE"],  # Test 4 modes
                "wait_time": 20,  # Extra wait after timeout
            },
            DiscoveryMode.YAML_ONLY: {
                "test_modes": False,
                "modes_to_test": [],
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
        self,
        mode: DiscoveryMode = DiscoveryMode.QUICK
    ) -> Dict[str, Any]:
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
            
            # Reset stop event
            self._stop_event.clear()
            
            # Update state to running
            await self.state_manager.update_state({
            "status": DiscoveryStatus.RUNNING,
            "mode": mode,
            "started_at": datetime.now(),
            "error": None,
        })
        
        # Start background task
        self._task = asyncio.create_task(self._run_discovery_loop(mode))
        
        logger.info(f"Discovery started in {mode.value} mode")
        
        return {
            "success": True,
            "mode": mode.value,
            "started_at": datetime.now().isoformat(),
        }
    
    async def stop_discovery(self) -> Dict[str, Any]:
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
        try:
            await asyncio.wait_for(self._task, timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Discovery task did not stop gracefully, cancelling")
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        # Update state
        await self.state_manager.update_state({
            "status": DiscoveryStatus.IDLE,
            "error": "Stopped by user",
        })
        
        logger.info("Discovery stopped")
        
        return {
            "success": True,
            "stopped_at": datetime.now().isoformat(),
        }
    
    async def _run_discovery_loop(self, mode: DiscoveryMode):
        """
        Main discovery loop (runs in background task).
        
        Args:
            mode: Discovery mode
        """
        try:
            logger.info(f"Starting discovery loop in {mode.value} mode")
            
            # Get mode configuration
            mode_config = self.mode_configs[mode]
            
            # Load spas from client
            spas = self.smarttub_client.spas
            
            if not spas:
                raise Exception("No spas found in account")
            
            logger.info(f"Found {len(spas)} spa(s)")
            
            # Process each spa
            results = {"spas": {}}
            
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
                spa_results = {
                    "spa_id": spa_id,
                    "lights": []
                }
                
                # Calculate total modes to test
                if mode_config["test_modes"]:
                    if mode_config["modes_to_test"] == "all":
                        # Import light modes dynamically
                        try:
                            from smarttub import SpaLight
                            all_modes = [m.name for m in SpaLight.LightMode]
                            modes_to_test = all_modes
                        except Exception as e:
                            logger.error(f"Could not load light modes: {e}")
                            modes_to_test = []
                    else:
                        modes_to_test = mode_config["modes_to_test"]
                    
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
                        "detected_modes": []
                    }
                    
                    # Test modes if enabled
                    if mode_config["test_modes"]:
                        logger.info(f"Testing {len(modes_to_test)} modes for {light_id}")
                        logger.info(f"Modes to test: {modes_to_test[:3]}...")  # DEBUG: Show first 3 modes
                        
                        for mode_name in modes_to_test:
                            logger.info(f"Testing mode {mode_name} on {light_id}")  # DEBUG
                            
                            # Check stop signal
                            if self._stop_event.is_set():
                                logger.info("Stop signal received, aborting discovery")
                                return
                            
                            # Test this mode
                            success = await self._test_light_mode(
                                light=light,
                                mode_name=mode_name,
                                wait_time=mode_config["wait_time"]
                            )
                            
                            if success:
                                light_results["detected_modes"].append(mode_name)
                                logger.debug(f"Mode {mode_name} works for {light_id}")
                            else:
                                logger.info(f"Mode {mode_name} failed for {light_id}")  # DEBUG
                            
                            # Update progress
                            state = await self.state_manager.get_state()
                            await self.state_manager.update_progress(
                                modes_tested=state.progress.modes_tested + 1
                            )
                    
                    # Add light to results
                    spa_results["lights"].append(light_results)
                    
                    # Update lights tested
                    await self.state_manager.update_progress(
                        lights_tested=light_idx + 1
                    )
                
                # Add spa to results
                results["spas"][spa_id] = spa_results
            
            # Save results to YAML
            yaml_path = await self._save_results_to_yaml(results)
            
            # Create discovery results
            discovery_results = DiscoveryResults(
                spas=results["spas"],
                yaml_path=str(yaml_path),
                total_lights=sum(len(s["lights"]) for s in results["spas"].values()),
                total_modes_detected=sum(
                    len(light["detected_modes"]) 
                    for spa in results["spas"].values() 
                    for light in spa["lights"]
                ),
            )
            
            # Update state to completed
            await self.state_manager.update_state({
                "status": DiscoveryStatus.COMPLETED,
                "completed_at": datetime.now(),
                "results": discovery_results,
            })
            
            logger.info(f"Discovery completed successfully: {discovery_results.total_lights} lights, "
                       f"{discovery_results.total_modes_detected} modes detected")
        
        except Exception as e:
            logger.exception(f"Discovery failed: {e}")
            
            # Update state to failed
            await self.state_manager.update_state({
                "status": DiscoveryStatus.FAILED,
                "completed_at": datetime.now(),
                "error": str(e),
            })
    
    async def _test_light_mode(
        self,
        light,
        mode_name: str,
        wait_time: int
    ) -> bool:
        """
        Test a single light mode.
        
        Uses the proven v0.2.3 approach:
        1. Try light.set_mode() (has built-in 10s wait)
        2. If timeout: wait extra time and verify manually
        3. Check mode matches (ignore intensity)
        
        Args:
            light: Light object
            mode_name: Mode name to test
            wait_time: Extra wait time if set_mode times out
        
        Returns:
            True if mode works, False otherwise
        """
        try:
            # Import dynamically
            from smarttub import SpaLight
            
            # Get mode enum
            try:
                mode = SpaLight.LightMode[mode_name]
            except KeyError:
                logger.warning(f"Unknown mode: {mode_name}")
                return False
            
            # Try using light.set_mode() (includes built-in state verification)
            try:
                logger.info(f"Calling set_mode({mode_name}, 50)...")
                await light.set_mode(mode, intensity=50)
                # Success - mode was set and verified
                logger.info(f"Mode {mode_name} verified by set_mode()")
                return True
                
            except Exception as e:
                error_str = str(e)
                logger.info(f"set_mode() raised: {error_str[:100]}")
                
                # Check for API rejection (invalid mode)
                if "400" in error_str or "404" in error_str:
                    logger.debug(f"API rejected mode {mode_name}: {e}")
                    return False
                
                # State change timeout - common for slow API
                # Solution: Wait extra time and verify manually
                if "State change not reflected" in error_str or "timeout" in error_str.lower():
                    logger.info(f"Mode {mode_name} timed out - verifying manually after {wait_time}s...")
                    
                    # Wait extra time for slow API
                    await asyncio.sleep(wait_time)
                    
                    try:
                        # Refresh spa status to get current light state
                        status = await light.spa.get_status_full()
                        logger.info(f"Got status, checking {len(status.lights)} lights...")
                        
                        # Find our light in the status
                        for status_light in status.lights:
                            if status_light.zone == light.zone:
                                current_mode = status_light.mode
                                logger.info(f"Light zone {light.zone}: Expected={mode_name}, Got={current_mode.name if current_mode else 'None'}")
                                
                                if current_mode and current_mode.name == mode_name:
                                    logger.info(f"Mode {mode_name} verified manually after timeout")
                                    return True
                                else:
                                    current = current_mode.name if current_mode else "None"
                                    logger.debug(f"Mode verification failed: expected {mode_name}, got {current}")
                                    return False
                        
                        logger.warning(f"Light zone {light.zone} not found in status")
                        return False
                            
                    except Exception as verify_error:
                        logger.error(f"Manual verification exception: {verify_error}")
                        return False
                
                # Other errors
                logger.error(f"Mode {mode_name} failed: {e}")
                return False
        
        except Exception as e:
            logger.error(f"Mode {mode_name} test exception: {e}")
            return False
    
    async def _save_results_to_yaml(
        self,
        results: Dict[str, Any]
    ) -> Path:
        """
        Save discovery results to YAML file.
        
        Args:
            results: Discovery results
        
        Returns:
            Path to saved YAML file
        """
        try:
            # Ensure directory exists
            self.yaml_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Prepare data structure
            discovered_items = {
                "discovered_items": {}
            }
            
            # Convert results to YAML format
            for spa_id, spa_data in results["spas"].items():
                discovered_items["discovered_items"][spa_id] = {
                    "lights": [
                        {
                            "id": light["id"],
                            "detected_modes": light["detected_modes"]
                        }
                        for light in spa_data["lights"]
                    ]
                }
            
            # Save to YAML
            with open(self.yaml_path, "w") as f:
                yaml.dump(
                    discovered_items,
                    f,
                    default_flow_style=False,
                    sort_keys=False
                )
            
            logger.info(f"Discovery results saved to {self.yaml_path}")
            return self.yaml_path
        
        except Exception as e:
            logger.error(f"Failed to save YAML: {e}")
            raise
