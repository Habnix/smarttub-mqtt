"""Conversion of SmartTub objects to discovery-artifact data."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def make_serializable(obj: Any) -> Any:
    """Return a JSON/YAML-serializable representation of a discovery value."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(key): make_serializable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_serializable(value) for value in obj]
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        try:
            return make_serializable(obj.to_dict())
        except Exception:
            logger.debug(
                "Object to_dict() failed during discovery serialization", exc_info=True
            )
    if hasattr(obj, "__dict__"):
        try:
            return make_serializable(
                {
                    key: value
                    for key, value in vars(obj).items()
                    if not key.startswith("_")
                }
            )
        except Exception:
            logger.debug(
                "Object attributes failed during discovery serialization",
                exc_info=True,
            )
    try:
        return str(obj)
    except Exception:  # noqa: BLE001
        return None
