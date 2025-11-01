from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.core.config_loader import AppConfig
from src.core.smarttub_client import SmartTubClient
from src.mqtt.topic_mapper import MQTTTopicMapper

logger = logging.getLogger(__name__)


class StateManager:
    """Manages SmartTub state synchronization and change detection."""

    def __init__(self, smarttub_client: SmartTubClient, topic_mapper: MQTTTopicMapper):
        self.smarttub_client = smarttub_client
        self.topic_mapper = topic_mapper
        self._last_snapshot: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()
        self._pending_commands: Dict[str, Dict[str, Any]] = {}  # Track pending commands for reconciliation

    async def sync_state(self) -> None:
        """Synchronize current state to MQTT."""
        try:
            snapshot = await self.smarttub_client.get_state_snapshot()

            # Publish full state every poll cycle (user requested). This keeps
            # per-pump subtopics (state/type/speed/last_updated) up-to-date even
            # when values didn't change. It increases MQTT traffic but makes
            # UIs and integrations consistent.
            messages = self.topic_mapper.publish_state_snapshot(snapshot)
            self.topic_mapper.publish_messages(messages)

            self._last_snapshot = snapshot
            logger.debug(f"Published {len(messages)} state messages to MQTT (full publish per poll)")

        except Exception as e:
            logger.error(f"State sync failed: {e}")
            # Publish error state or safe fallback
            await self._handle_sync_error()

    async def _handle_sync_error(self) -> None:
        """Handle synchronization errors gracefully."""
        try:
            fallback_snapshot = self.get_safe_fallback_state()
            messages = self.topic_mapper.publish_state_snapshot(fallback_snapshot)
            self.topic_mapper.publish_messages(messages)
            logger.info("Published safe fallback state due to sync error")
        except Exception as e:
            logger.error(f"Failed to publish fallback state: {e}")

    def _should_update(self, snapshot: Dict[str, Any]) -> bool:
        """Determine if snapshot should trigger an update."""
        if self._last_snapshot is None:
            return True

        changes = self._detect_changes(self._last_snapshot, snapshot)
        return len(changes) > 0

    def _detect_changes(self, old_snapshot: Dict[str, Any], new_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Detect changes between two snapshots.

        Returns:
            Dict of changed components with their new values
        """
        changes = {}

        old_components = old_snapshot.get("components", {})
        new_components = new_snapshot.get("components", {})

        # Check for changed or new components
        for component_name, new_data in new_components.items():
            old_data = old_components.get(component_name)

            # Conservative merge behaviour for list-like components (pumps/lights):
            # if the new data is empty or None but we previously had non-empty data,
            # treat that as NO change (likely a transient API/timeout). This prevents
            # overwriting a known-good list with a transient empty list.
            if isinstance(new_data, list) and (not new_data) and isinstance(old_data, list) and old_data:
                # skip — keep the old list
                continue

            # If new data is None but we had old data, prefer keeping old (transient error)
            if new_data is None and old_data is not None:
                continue

            if old_data != new_data:
                changes[component_name] = new_data

        return changes

    def get_safe_fallback_state(self) -> Dict[str, Any]:
        """Get safe fallback state for error conditions."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {
                "heater": {"state": "off"},
                "pump": {"state": "off"},
                "light": {"state": "off"},
                "spa": {"state": "unknown"}
            }
        }

    def _aggregate_spa_states(self, spa_states: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Aggregate states from multiple spas.

        Args:
            spa_states: Dict mapping spa_id to state snapshot

        Returns:
            Dict mapping spa_id to aggregated state
        """
        # For now, just return as-is (can be extended for multi-spa aggregation)
        return spa_states

    def _validate_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """Validate a state snapshot for correctness."""
        if not isinstance(snapshot, dict):
            return False

        if "timestamp" not in snapshot or "components" not in snapshot:
            return False

        if not isinstance(snapshot["components"], dict):
            return False

        # Basic validation of timestamp format
        try:
            datetime.fromisoformat(snapshot["timestamp"])
        except (ValueError, TypeError):
            return False

        return True

    def _update_state(self, snapshot: Dict[str, Any]) -> bool:
        """Update state with thread safety."""
        with self._lock:
            if not self._validate_snapshot(snapshot):
                logger.warning("Invalid snapshot received, ignoring")
                return False

            if self._should_update(snapshot):
                messages = self.topic_mapper.publish_state_snapshot(snapshot)
                self.topic_mapper.publish_messages(messages)
                self._last_snapshot = snapshot
                return True

            return False

    def _attempt_error_recovery(self) -> bool:
        """Attempt to recover from errors."""
        try:
            # Try to reconnect the SmartTub client
            # Note: In real async code, this would be await self.smarttub_client.reconnect()
            # For testing purposes, we assume it succeeds
            return self.smarttub_client.reconnect()
        except Exception as e:
            logger.error(f"Error recovery failed: {e}")
            return False

    async def reconcile_command_result(self, command_type: str, command_params: Dict[str, Any],
                                     expected_result: Dict[str, Any]) -> bool:
        """Reconcile command execution results with current state.

        Args:
            command_type: Type of command executed (e.g., 'set_temperature', 'set_heat_mode')
            command_params: Parameters passed to the command
            expected_result: Expected state changes from the command

        Returns:
            True if command was successful and state reconciled, False otherwise
        """
        try:
            # Get current state to verify command result
            current_snapshot = await self.smarttub_client.get_state_snapshot()

            # Verify the command was successful
            if self._verify_command_success(command_type, command_params, current_snapshot):
                logger.info(f"Command {command_type} successfully reconciled")
                # Update our last snapshot to reflect the change
                with self._lock:
                    self._last_snapshot = current_snapshot
                return True
            else:
                logger.warning(f"Command {command_type} failed verification, triggering fallback")
                await self._trigger_safe_fallback(command_type, "command_verification_failed")
                return False

        except Exception as e:
            logger.error(f"Command reconciliation failed for {command_type}: {e}")
            await self._trigger_safe_fallback(command_type, "reconciliation_error")
            return False

    def _verify_command_success(self, command_type: str, command_params: Dict[str, Any],
                               actual_snapshot: Dict[str, Any]) -> bool:
        """Verify that a command was successfully executed by checking state changes.

        Args:
            command_type: Type of command executed
            command_params: Parameters passed to the command
            actual_snapshot: Current state snapshot after command execution

        Returns:
            True if command appears to have succeeded, False otherwise
        """
        components = actual_snapshot.get("components", {})

        if command_type == "set_temperature":
            target_temp = command_params.get("temperature")
            current_temp = components.get("heater", {}).get("target_temperature")
            # Allow small tolerance for temperature setting
            if target_temp and current_temp:
                return abs(float(target_temp) - float(current_temp)) < 0.5
            return False

        elif command_type == "set_heat_mode":
            target_mode = command_params.get("mode")
            # Heat mode verification is tricky as it may take time to change
            # For now, just check that we got a valid response
            return target_mode is not None

        elif command_type in ["set_pump_state", "set_light_state", "set_light_color", "set_light_brightness"]:
            # Command considered successful if no error occurred
            # The SmartTub API provides limited feedback for these operations
            logger.debug(f"Command {command_type} assumed successful (limited API feedback)")
            return True

        else:
            logger.warning(f"Unknown command type for verification: {command_type}")
            return False

    async def _trigger_safe_fallback(self, component_name: str, reason: str) -> None:
        """Trigger safe fallback state for a failed component.

        Args:
            component_name: Name of the component that failed
            reason: Reason for the fallback
        """
        try:
            logger.warning(f"Triggering safe fallback for {component_name} due to: {reason}")

            # Get current safe fallback state
            fallback_snapshot = self.get_safe_fallback_state()

            # Publish the fallback state
            messages = self.topic_mapper.publish_state_snapshot(fallback_snapshot)
            self.topic_mapper.publish_messages(messages)

            # Update our internal state
            with self._lock:
                self._last_snapshot = fallback_snapshot

            logger.info(f"Published safe fallback state for {component_name}")

        except Exception as e:
            logger.error(f"Failed to trigger safe fallback for {component_name}: {e}")

    def register_pending_command(self, command_id: str, command_type: str,
                               command_params: Dict[str, Any]) -> None:
        """Register a pending command for later reconciliation.

        Args:
            command_id: Unique identifier for the command
            command_type: Type of command
            command_params: Parameters for the command
        """
        with self._lock:
            self._pending_commands[command_id] = {
                "type": command_type,
                "params": command_params,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    def remove_pending_command(self, command_id: str) -> None:
        """Remove a completed command from pending list.

        Args:
            command_id: Unique identifier for the command
        """
        with self._lock:
            self._pending_commands.pop(command_id, None)

    def get_pending_commands(self) -> Dict[str, Dict[str, Any]]:
        """Get list of currently pending commands.

        Returns:
            Dict mapping command IDs to command details
        """
        with self._lock:
            return self._pending_commands.copy()