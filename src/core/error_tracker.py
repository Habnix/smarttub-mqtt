"""Central error tracking and recovery management for smarttub-mqtt."""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any
from threading import Lock


logger = logging.getLogger("smarttub.core")


class ErrorSeverity(Enum):
    """Error severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for tracking different subsystems."""

    DISCOVERY = "discovery"
    YAML_PARSING = "yaml_parsing"
    MQTT_CONNECTION = "mqtt_connection"
    MQTT_PUBLISH = "mqtt_publish"
    LOGGING_SYSTEM = "logging_system"
    SMARTTUB_API = "smarttub_api"
    CONFIGURATION = "configuration"
    WEB_UI = "webui"
    COMMAND_EXECUTION = "command_execution"
    STATE_SYNC = "state_sync"


@dataclass
class ErrorEntry:
    """Single error entry with metadata."""

    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    timestamp: float = field(default_factory=time.time)
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    recovery_attempted: bool = False
    recovery_successful: Optional[bool] = None
    recovery_timestamp: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert error entry to dictionary."""
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": datetime.fromtimestamp(
                self.timestamp, tz=timezone.utc
            ).isoformat(),
            "error_code": self.error_code,
            "details": self.details or {},
            "recovery": {
                "attempted": self.recovery_attempted,
                "successful": self.recovery_successful,
                "timestamp": datetime.fromtimestamp(
                    self.recovery_timestamp, tz=timezone.utc
                ).isoformat()
                if self.recovery_timestamp
                else None,
            },
        }


class ErrorTracker:
    """Centralized error tracking and recovery management.

    Tracks errors across all subsystems, provides recovery hooks,
    and publishes error state to MQTT meta-topics.
    """

    def __init__(self, max_errors: int = 100):
        """Initialize error tracker.

        Args:
            max_errors: Maximum number of errors to keep in memory (FIFO)
        """
        self._max_errors = max_errors
        self._errors: List[ErrorEntry] = []
        self._error_counts: Dict[ErrorCategory, int] = {}
        self._last_error_time: Dict[ErrorCategory, float] = {}
        self._recovery_callbacks: Dict[ErrorCategory, List[callable]] = {}
        self._lock = Lock()

        # Initialize counts
        for category in ErrorCategory:
            self._error_counts[category] = 0

    def track_error(
        self,
        category: ErrorCategory,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> ErrorEntry:
        """Track a new error.

        Args:
            category: Error category
            message: Human-readable error message
            severity: Error severity level
            error_code: Optional error code for categorization
            details: Optional additional details

        Returns:
            Created error entry
        """
        entry = ErrorEntry(
            category=category,
            severity=severity,
            message=message,
            error_code=error_code,
            details=details or {},
        )

        with self._lock:
            # Add to list (FIFO)
            self._errors.append(entry)
            if len(self._errors) > self._max_errors:
                self._errors.pop(0)

            # Update counts
            self._error_counts[category] += 1
            self._last_error_time[category] = entry.timestamp

        # Log the error
        log_level = {
            ErrorSeverity.INFO: logging.INFO,
            ErrorSeverity.WARNING: logging.WARNING,
            ErrorSeverity.ERROR: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL,
        }.get(severity, logging.ERROR)

        logger.log(
            log_level,
            f"[{category.value}] {message}",
            extra={"error_code": error_code, "details": details},
        )

        return entry

    def attempt_recovery(
        self, category: ErrorCategory, recovery_action: Optional[callable] = None
    ) -> bool:
        """Attempt recovery for a specific error category.

        Args:
            category: Error category to recover
            recovery_action: Optional custom recovery action (callable)

        Returns:
            True if recovery successful, False otherwise
        """
        # Find most recent error for this category
        with self._lock:
            recent_errors = [
                e
                for e in reversed(self._errors)
                if e.category == category and not e.recovery_attempted
            ]
            if not recent_errors:
                return True  # No pending errors

            error_entry = recent_errors[0]
            error_entry.recovery_attempted = True

        # Execute recovery action
        success = False
        try:
            if recovery_action:
                success = recovery_action()
            else:
                # Try registered callbacks
                callbacks = self._recovery_callbacks.get(category, [])
                for callback in callbacks:
                    try:
                        if callback(error_entry):
                            success = True
                            break
                    except Exception as e:
                        logger.warning(
                            f"Recovery callback failed for {category.value}: {e}"
                        )

        except Exception as e:
            logger.error(f"Recovery action failed for {category.value}: {e}")
            success = False

        # Update error entry
        with self._lock:
            error_entry.recovery_successful = success
            error_entry.recovery_timestamp = time.time()

        logger.info(
            f"Recovery {'succeeded' if success else 'failed'} for {category.value}"
        )
        return success

    def register_recovery_callback(
        self, category: ErrorCategory, callback: callable
    ) -> None:
        """Register a recovery callback for a specific category.

        Args:
            category: Error category
            callback: Recovery callback (should return bool for success/failure)
        """
        if category not in self._recovery_callbacks:
            self._recovery_callbacks[category] = []
        self._recovery_callbacks[category].append(callback)

    def get_errors(
        self,
        category: Optional[ErrorCategory] = None,
        severity: Optional[ErrorSeverity] = None,
        limit: Optional[int] = None,
    ) -> List[ErrorEntry]:
        """Get errors filtered by category and/or severity.

        Args:
            category: Optional category filter
            severity: Optional severity filter
            limit: Optional limit on number of errors returned

        Returns:
            List of error entries matching filters
        """
        with self._lock:
            errors = list(self._errors)

        # Apply filters
        if category:
            errors = [e for e in errors if e.category == category]
        if severity:
            errors = [e for e in errors if e.severity == severity]

        # Most recent first
        errors.reverse()

        # Apply limit
        if limit:
            errors = errors[:limit]

        return errors

    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of all errors.

        Returns:
            Dictionary with error statistics and recent errors
        """
        with self._lock:
            total_errors = len(self._errors)
            category_counts = dict(self._error_counts)
            last_error_times = {
                cat.value: datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                for cat, ts in self._last_error_time.items()
            }

            # Recent errors (last 10)
            recent = [e.to_dict() for e in list(reversed(self._errors))[:10]]

            # Critical/error count
            critical_count = sum(
                1 for e in self._errors if e.severity == ErrorSeverity.CRITICAL
            )
            error_count = sum(
                1 for e in self._errors if e.severity == ErrorSeverity.ERROR
            )

        return {
            "total_errors": total_errors,
            "critical_count": critical_count,
            "error_count": error_count,
            "by_category": {
                cat.value: count for cat, count in category_counts.items() if count > 0
            },
            "last_error_time": last_error_times,
            "recent_errors": recent,
        }

    def clear_errors(self, category: Optional[ErrorCategory] = None) -> int:
        """Clear errors, optionally filtered by category.

        Args:
            category: Optional category to clear (clears all if None)

        Returns:
            Number of errors cleared
        """
        with self._lock:
            if category:
                original_count = len(self._errors)
                self._errors = [e for e in self._errors if e.category != category]
                cleared = original_count - len(self._errors)
                self._error_counts[category] = 0
                if category in self._last_error_time:
                    del self._last_error_time[category]
            else:
                cleared = len(self._errors)
                self._errors.clear()
                for cat in ErrorCategory:
                    self._error_counts[cat] = 0
                self._last_error_time.clear()

        logger.info(
            f"Cleared {cleared} errors"
            + (f" for category {category.value}" if category else "")
        )
        return cleared

    def get_subsystem_status(self) -> Dict[str, str]:
        """Get status of all subsystems based on error state.

        Returns:
            Dictionary mapping category to status (healthy/degraded/failed)
        """
        status = {}

        with self._lock:
            for category in ErrorCategory:
                # Check recent errors (last 5 minutes)
                now = time.time()
                five_minutes_ago = now - 300

                recent_errors = [
                    e
                    for e in self._errors
                    if e.category == category and e.timestamp > five_minutes_ago
                ]

                if not recent_errors:
                    status[category.value] = "healthy"
                else:
                    # Check severity
                    has_critical = any(
                        e.severity == ErrorSeverity.CRITICAL for e in recent_errors
                    )
                    has_error = any(
                        e.severity == ErrorSeverity.ERROR for e in recent_errors
                    )

                    if has_critical or (has_error and len(recent_errors) >= 3):
                        status[category.value] = "failed"
                    elif has_error:
                        status[category.value] = "degraded"
                    else:
                        status[category.value] = "healthy"

        return status
