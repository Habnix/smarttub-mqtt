"""
Discovery State Management.

Provides thread-safe state management for the background discovery process
with observer pattern for real-time updates.
"""

import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, List, Callable, Dict, Any
import logging

logger = logging.getLogger(__name__)


class DiscoveryStatus(str, Enum):
    """Discovery process status."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DiscoveryMode(str, Enum):
    """Discovery test modes."""
    FULL = "full"          # Test all 18 modes per light (slow, ~20 min)
    QUICK = "quick"        # Test subset of modes (fast, ~5 min)
    YAML_ONLY = "yaml_only"  # Just load and publish YAML (instant)


@dataclass
class DiscoveryProgress:
    """Progress tracking for discovery process."""
    
    current_spa: Optional[str] = None
    current_light: Optional[str] = None
    
    lights_total: int = 0
    lights_tested: int = 0
    
    modes_total: int = 0
    modes_tested: int = 0
    
    percentage: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def calculate_percentage(self) -> float:
        """Calculate completion percentage."""
        if self.modes_total == 0:
            return 0.0
        return round((self.modes_tested / self.modes_total) * 100, 1)
    
    def update_percentage(self):
        """Update percentage based on current progress."""
        self.percentage = self.calculate_percentage()


@dataclass
class DiscoveryResults:
    """Discovery results container."""
    
    spas: Dict[str, Any] = field(default_factory=dict)
    yaml_path: Optional[str] = None
    total_lights: int = 0
    total_modes_detected: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "spas": self.spas,
            "yaml_path": self.yaml_path,
            "total_lights": self.total_lights,
            "total_modes_detected": self.total_modes_detected,
        }


@dataclass
class DiscoveryState:
    """
    Central state container for discovery process.
    
    Thread-safe access provided by DiscoveryStateManager.
    """
    
    status: DiscoveryStatus = DiscoveryStatus.IDLE
    mode: Optional[DiscoveryMode] = None
    
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    progress: DiscoveryProgress = field(default_factory=DiscoveryProgress)
    results: Optional[DiscoveryResults] = None
    
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status.value,
            "mode": self.mode.value if self.mode else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "progress": self.progress.to_dict(),
            "results": self.results.to_dict() if self.results else None,
            "error": self.error,
        }
    
    def reset(self):
        """Reset state to idle."""
        self.status = DiscoveryStatus.IDLE
        self.mode = None
        self.started_at = None
        self.completed_at = None
        self.progress = DiscoveryProgress()
        self.results = None
        self.error = None


class DiscoveryStateManager:
    """
    Thread-safe state manager for discovery process.
    
    Provides:
    - Atomic state updates with asyncio.Lock
    - Observer pattern for state change notifications
    - Read/Write access to discovery state
    
    Usage:
        manager = DiscoveryStateManager()
        
        # Subscribe to state changes
        async def on_state_change(state: DiscoveryState):
            print(f"Status: {state.status}")
        
        manager.subscribe(on_state_change)
        
        # Update state
        await manager.update_state({"status": DiscoveryStatus.RUNNING})
    """
    
    def __init__(self):
        """Initialize state manager."""
        self._state = DiscoveryState()
        self._lock = asyncio.Lock()
        self._observers: List[Callable[[DiscoveryState], None]] = []
        
        logger.debug("DiscoveryStateManager initialized")
    
    async def get_state(self) -> DiscoveryState:
        """
        Get current discovery state (thread-safe).
        
        Returns:
            Current DiscoveryState (copy)
        """
        async with self._lock:
            # Return a copy to prevent external modifications
            return DiscoveryState(
                status=self._state.status,
                mode=self._state.mode,
                started_at=self._state.started_at,
                completed_at=self._state.completed_at,
                progress=DiscoveryProgress(**self._state.progress.to_dict()),
                results=self._state.results,
                error=self._state.error,
            )
    
    async def update_state(self, updates: Dict[str, Any]) -> DiscoveryState:
        """
        Update discovery state atomically.
        
        Args:
            updates: Dictionary with state updates
                Supported keys:
                - status: DiscoveryStatus
                - mode: DiscoveryMode
                - started_at: datetime
                - completed_at: datetime
                - error: str
                - progress: dict or DiscoveryProgress
                - results: dict or DiscoveryResults
        
        Returns:
            Updated state (copy)
        """
        async with self._lock:
            # Update status
            if "status" in updates:
                if isinstance(updates["status"], str):
                    self._state.status = DiscoveryStatus(updates["status"])
                else:
                    self._state.status = updates["status"]
            
            # Update mode
            if "mode" in updates:
                if isinstance(updates["mode"], str):
                    self._state.mode = DiscoveryMode(updates["mode"])
                else:
                    self._state.mode = updates["mode"]
            
            # Update timestamps
            if "started_at" in updates:
                self._state.started_at = updates["started_at"]
            
            if "completed_at" in updates:
                self._state.completed_at = updates["completed_at"]
            
            # Update error
            if "error" in updates:
                self._state.error = updates["error"]
            
            # Update progress
            if "progress" in updates:
                if isinstance(updates["progress"], dict):
                    # Merge progress dict
                    for key, value in updates["progress"].items():
                        setattr(self._state.progress, key, value)
                    # Recalculate percentage
                    self._state.progress.update_percentage()
                else:
                    self._state.progress = updates["progress"]
            
            # Update results
            if "results" in updates:
                if isinstance(updates["results"], dict):
                    self._state.results = DiscoveryResults(**updates["results"])
                else:
                    self._state.results = updates["results"]
            
            # Create copy of updated state (inside lock)
            updated_state = DiscoveryState(
                status=self._state.status,
                mode=self._state.mode,
                started_at=self._state.started_at,
                completed_at=self._state.completed_at,
                progress=DiscoveryProgress(**self._state.progress.to_dict()),
                results=self._state.results,
                error=self._state.error,
            )
        
        # Notify observers (outside lock to prevent deadlock)
        await self._notify_observers(updated_state)
        
        logger.debug(f"State updated: status={updated_state.status.value}, "
                    f"progress={updated_state.progress.percentage}%")
        
        return updated_state
    
    async def reset(self) -> DiscoveryState:
        """
        Reset state to idle.
        
        Returns:
            Reset state
        """
        async with self._lock:
            self._state.reset()
            # Create copy inside lock
            updated_state = DiscoveryState(
                status=self._state.status,
                mode=self._state.mode,
                started_at=self._state.started_at,
                completed_at=self._state.completed_at,
                progress=DiscoveryProgress(**self._state.progress.to_dict()),
                results=self._state.results,
                error=self._state.error,
            )
        
        await self._notify_observers(updated_state)
        
        logger.debug("State reset to idle")
        return updated_state
    
    def subscribe(self, callback: Callable[[DiscoveryState], None]):
        """
        Subscribe to state changes.
        
        Args:
            callback: Async function called on state changes
                Signature: async def callback(state: DiscoveryState)
        """
        if callback not in self._observers:
            self._observers.append(callback)
            logger.debug(f"Observer subscribed: {callback.__name__}")
    
    def unsubscribe(self, callback: Callable[[DiscoveryState], None]):
        """
        Unsubscribe from state changes.
        
        Args:
            callback: Previously subscribed callback
        """
        if callback in self._observers:
            self._observers.remove(callback)
            logger.debug(f"Observer unsubscribed: {callback.__name__}")
    
    async def _notify_observers(self, state: DiscoveryState):
        """
        Notify all observers of state change.
        
        Args:
            state: Current state to send to observers
        """
        if not self._observers:
            return
        
        logger.debug(f"Notifying {len(self._observers)} observers")
        
        # Call all observers concurrently
        tasks = []
        for observer in self._observers:
            try:
                # Check if observer is async
                if asyncio.iscoroutinefunction(observer):
                    tasks.append(observer(state))
                else:
                    # Sync observer - run in executor
                    loop = asyncio.get_event_loop()
                    tasks.append(loop.run_in_executor(None, observer, state))
            except Exception as e:
                logger.error(f"Error notifying observer {observer.__name__}: {e}")
        
        # Wait for all observers
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def update_progress(
        self,
        current_spa: Optional[str] = None,
        current_light: Optional[str] = None,
        lights_total: Optional[int] = None,
        lights_tested: Optional[int] = None,
        modes_total: Optional[int] = None,
        modes_tested: Optional[int] = None,
    ) -> DiscoveryState:
        """
        Convenient method to update progress fields.
        
        Args:
            current_spa: Current spa being tested
            current_light: Current light being tested
            lights_total: Total number of lights
            lights_tested: Number of lights tested
            modes_total: Total modes to test
            modes_tested: Number of modes tested
        
        Returns:
            Updated state
        """
        progress_updates = {}
        
        if current_spa is not None:
            progress_updates["current_spa"] = current_spa
        if current_light is not None:
            progress_updates["current_light"] = current_light
        if lights_total is not None:
            progress_updates["lights_total"] = lights_total
        if lights_tested is not None:
            progress_updates["lights_tested"] = lights_tested
        if modes_total is not None:
            progress_updates["modes_total"] = modes_total
        if modes_tested is not None:
            progress_updates["modes_tested"] = modes_tested
        
        return await self.update_state({"progress": progress_updates})
    
    def get_state_sync(self) -> Dict[str, Any]:
        """
        Get state synchronously (for non-async contexts).
        
        Returns:
            State as dictionary
        """
        # Note: This is not thread-safe, but useful for quick checks
        return self._state.to_dict()
