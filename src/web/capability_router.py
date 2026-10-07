"""HTTP endpoint for detected SmartTub capabilities."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from src.core.capability_detector import CapabilityDetector
from src.core.config_loader import AppConfig
from src.web.errors import internal_server_error

logger = logging.getLogger(__name__)


def create_capability_router(
    config: AppConfig, capability_detector: CapabilityDetector | None
) -> APIRouter:
    """Create the capability API with explicit, read-only dependencies."""
    router = APIRouter(tags=["capabilities"])

    @router.get("/api/capabilities", response_model=dict[str, Any])
    async def get_capabilities() -> dict[str, Any]:
        """Get detected capabilities and their MQTT metadata topics."""
        try:
            profiles = (
                capability_detector.get_cached_profiles()
                if capability_detector is not None
                else {}
            )
            return {
                "timestamp": datetime.now(UTC).isoformat(),
                "spas": profiles,
                "mqtt_topics": {
                    "base_topic": config.mqtt.base_topic,
                    "capability_meta_topics": [
                        f"{config.mqtt.base_topic}/spa/{{spa_id}}/capability/meta"
                        for spa_id in profiles
                    ],
                },
                **(
                    {}
                    if capability_detector is not None
                    else {
                        "note": "Capability detector not available - showing static capabilities"
                    }
                ),
            }
        except Exception as exc:
            raise internal_server_error(logger, "Failed to get capabilities") from exc

    return router
