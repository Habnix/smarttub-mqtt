"""HTTP endpoints for state snapshots and application health."""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.core.runtime_health import RuntimeHealth
from src.core.state_manager import StateManager
from src.web.errors import internal_server_error

logger = logging.getLogger(__name__)


def create_state_router(
    state_manager: StateManager, runtime_health: RuntimeHealth
) -> APIRouter:
    """Create routes that expose the last synchronized SmartTub state."""
    router = APIRouter(tags=["state"])

    @router.get("/api/state", response_model=dict[str, Any])
    async def get_state() -> dict[str, Any]:
        """Get the last observation together with explicit quality metadata."""
        try:
            snapshot = state_manager.get_latest_snapshot()
            if snapshot is None:
                return cast(dict[str, Any], state_manager.get_safe_fallback_state())
            return cast(dict[str, Any], snapshot)
        except Exception as exc:
            raise internal_server_error(logger, "Failed to get state") from exc

    @router.get("/live")
    async def liveness_check() -> dict[str, Any]:
        """Return process liveness without dependency details."""
        return runtime_health.liveness()

    @router.get("/ready", response_model=None)
    async def readiness_check() -> JSONResponse:
        """Return dependency readiness and HTTP 503 while degraded."""
        report = runtime_health.readiness()
        return JSONResponse(
            status_code=200 if report["status"] == "ready" else 503,
            content=report,
        )

    @router.get("/health")
    async def legacy_health_check() -> dict[str, str]:
        """Retain the historical liveness endpoint for compatibility."""
        live = runtime_health.liveness()
        return {
            "status": "healthy",
            "timestamp": str(live["timestamp"]),
        }

    return router
