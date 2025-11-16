"""Discovery Progress Tracking

Tracks the progress of spa discovery operations and provides real-time status updates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class DiscoveryPhase(Enum):
    """Discovery phases"""

    INITIALIZING = "initializing"
    CONNECTING = "connecting"
    FETCHING_SPAS = "fetching_spas"
    PROBING_SPA = "probing_spa"
    PROBING_PUMPS = "probing_pumps"
    PROBING_LIGHTS = "probing_lights"
    PROBING_HEATER = "probing_heater"
    PROBING_STATUS = "probing_status"
    WRITING_YAML = "writing_yaml"
    PUBLISHING_MQTT = "publishing_mqtt"
    COMPLETED = "completed"
    FAILED = "failed"


class ComponentType(Enum):
    """Component types being discovered"""

    SPA = "spa"
    PUMP = "pump"
    LIGHT = "light"
    HEATER = "heater"
    STATUS = "status"


@dataclass
class ComponentProgress:
    """Progress for a single component"""

    component_type: ComponentType
    component_id: str
    name: Optional[str] = None
    phase: DiscoveryPhase = DiscoveryPhase.INITIALIZING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    example_info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "component_type": self.component_type.value,
            "component_id": self.component_id,
            "name": self.name,
            "phase": self.phase.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "error": self.error,
            "example_info": self.example_info,
        }


@dataclass
class SpaProgress:
    """Progress for a single spa discovery"""

    spa_id: str
    spa_name: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    total_components: int = 0
    completed_components: int = 0
    current_component: Optional[ComponentProgress] = None
    components: List[ComponentProgress] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def progress_percent(self) -> int:
        """Calculate progress percentage"""
        if self.total_components == 0:
            return 0
        return int((self.completed_components / self.total_components) * 100)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "spa_id": self.spa_id,
            "spa_name": self.spa_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "total_components": self.total_components,
            "completed_components": self.completed_components,
            "progress_percent": self.progress_percent,
            "current_component": self.current_component.to_dict()
            if self.current_component
            else None,
            "components": [c.to_dict() for c in self.components],
            "error": self.error,
        }


class DiscoveryProgressTracker:
    """Tracks progress of discovery operations across all spas"""

    def __init__(self):
        self._lock = Lock()
        self._spas: Dict[str, SpaProgress] = {}
        self._overall_phase: DiscoveryPhase = DiscoveryPhase.INITIALIZING
        self._started_at: Optional[datetime] = None
        self._completed_at: Optional[datetime] = None
        self._total_spas: int = 0
        self._completed_spas: int = 0

    def start_discovery(self, total_spas: int) -> None:
        """Start a new discovery session"""
        with self._lock:
            self._spas.clear()
            self._overall_phase = DiscoveryPhase.INITIALIZING
            self._started_at = datetime.now(timezone.utc)
            self._completed_at = None
            self._total_spas = total_spas
            self._completed_spas = 0
            logger.info(f"Discovery started for {total_spas} spa(s)")

    def start_spa(self, spa_id: str, spa_name: Optional[str] = None) -> None:
        """Start probing a spa"""
        with self._lock:
            self._spas[spa_id] = SpaProgress(spa_id=spa_id, spa_name=spa_name)
            logger.info(f"Started probing spa: {spa_id} ({spa_name})")

    def set_spa_component_count(self, spa_id: str, total_components: int) -> None:
        """Set expected number of components for a spa"""
        with self._lock:
            if spa_id in self._spas:
                self._spas[spa_id].total_components = total_components

    def start_component(
        self,
        spa_id: str,
        component_type: ComponentType,
        component_id: str,
        name: Optional[str] = None,
    ) -> None:
        """Start probing a component"""
        with self._lock:
            if spa_id not in self._spas:
                logger.warning(f"Spa {spa_id} not found in progress tracker")
                return

            component = ComponentProgress(
                component_type=component_type, component_id=component_id, name=name
            )
            self._spas[spa_id].current_component = component
            self._spas[spa_id].components.append(component)
            logger.debug(f"Started probing {component_type.value}: {component_id}")

    def update_component_phase(
        self,
        spa_id: str,
        component_id: str,
        phase: DiscoveryPhase,
        example_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update component phase and optionally add example info"""
        with self._lock:
            if spa_id not in self._spas:
                return

            spa = self._spas[spa_id]
            for component in spa.components:
                if component.component_id == component_id:
                    component.phase = phase
                    if example_info:
                        component.example_info = example_info
                    break

    def complete_component(
        self,
        spa_id: str,
        component_id: str,
        example_info: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Mark a component as completed"""
        with self._lock:
            if spa_id not in self._spas:
                return

            spa = self._spas[spa_id]
            for component in spa.components:
                if component.component_id == component_id:
                    component.completed_at = datetime.now(timezone.utc)
                    component.phase = (
                        DiscoveryPhase.FAILED if error else DiscoveryPhase.COMPLETED
                    )
                    if example_info:
                        component.example_info = example_info
                    if error:
                        component.error = error
                    spa.completed_components += 1
                    break

            # Clear current component if this was it
            if (
                spa.current_component
                and spa.current_component.component_id == component_id
            ):
                spa.current_component = None

    def complete_spa(self, spa_id: str, error: Optional[str] = None) -> None:
        """Mark a spa as completed"""
        with self._lock:
            if spa_id not in self._spas:
                return

            spa = self._spas[spa_id]
            spa.completed_at = datetime.now(timezone.utc)
            if error:
                spa.error = error
            self._completed_spas += 1
            logger.info(f"Completed probing spa: {spa_id} ({spa.progress_percent}%)")

    def set_overall_phase(self, phase: DiscoveryPhase) -> None:
        """Set overall discovery phase"""
        with self._lock:
            self._overall_phase = phase
            if phase == DiscoveryPhase.COMPLETED or phase == DiscoveryPhase.FAILED:
                self._completed_at = datetime.now(timezone.utc)
                logger.info(f"Discovery {phase.value}")

    def get_progress(self) -> Dict[str, Any]:
        """Get current progress snapshot"""
        with self._lock:
            overall_percent = 0
            if self._total_spas > 0:
                overall_percent = int((self._completed_spas / self._total_spas) * 100)

            return {
                "overall_phase": self._overall_phase.value,
                "started_at": self._started_at.isoformat()
                if self._started_at
                else None,
                "completed_at": self._completed_at.isoformat()
                if self._completed_at
                else None,
                "total_spas": self._total_spas,
                "completed_spas": self._completed_spas,
                "overall_percent": overall_percent,
                "spas": {spa_id: spa.to_dict() for spa_id, spa in self._spas.items()},
            }

    def get_spa_progress(self, spa_id: str) -> Optional[Dict[str, Any]]:
        """Get progress for a specific spa"""
        with self._lock:
            spa = self._spas.get(spa_id)
            return spa.to_dict() if spa else None
