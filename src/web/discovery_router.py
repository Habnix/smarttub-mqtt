"""HTTP endpoints for observing and controlling item discovery."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from starlette.requests import Request

from src.web.errors import internal_server_error

logger = logging.getLogger(__name__)


def _discovery_failure(
    action: str, reason: object = None, status_code: int = 400
) -> HTTPException:
    """Return a safe error after the coordinator already logged the cause."""
    logger.warning("%s: %s", action, reason or "no details available")
    return HTTPException(status_code=status_code, detail=action)


def create_discovery_router(
    progress_tracker: Any = None, discovery_coordinator: Any = None
) -> APIRouter:
    """Create discovery APIs with their collaborators supplied explicitly."""
    router = APIRouter(tags=["discovery"])

    @router.get("/api/discovery/progress", response_model=dict[str, Any])
    async def get_discovery_progress() -> dict[str, Any]:
        """Get discovery progress status (T059)."""
        try:
            if progress_tracker:
                return {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "progress": progress_tracker.get_progress(),
                    "available": True,
                }
            return {
                "timestamp": datetime.now(UTC).isoformat(),
                "progress": {},
                "available": False,
                "message": "Progress tracker not available",
            }
        except Exception as exc:
            raise internal_server_error(
                logger, "Failed to get discovery progress"
            ) from exc

    @router.get("/api/discovery/progress/{spa_id}", response_model=dict[str, Any])
    async def get_spa_progress(spa_id: str) -> dict[str, Any]:
        """Get discovery progress for a specific spa (T059)."""
        try:
            if progress_tracker:
                spa_progress = progress_tracker.get_spa_progress(spa_id)
                if spa_progress:
                    return {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "spa_progress": spa_progress,
                        "available": True,
                    }
                raise HTTPException(
                    status_code=404,
                    detail=f"Spa {spa_id} not found in progress tracker",
                )
            raise HTTPException(
                status_code=503, detail="Progress tracker not available"
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise internal_server_error(logger, "Failed to get spa progress") from exc

    @router.get("/api/discovery/status", response_model=dict[str, Any])
    async def get_background_discovery_status() -> dict[str, Any]:
        """Get current background discovery status."""
        try:
            if discovery_coordinator:
                status = await discovery_coordinator.get_status()
                if status.get("success") is False:
                    logger.warning(
                        "Discovery status is unavailable: %s", status.get("error")
                    )
                    return {"success": False, "error": "Discovery status unavailable"}
                if status.get("error"):
                    logger.warning("Discovery reported an error: %s", status["error"])
                    status = {**status, "error": "Discovery reported an error"}
                return status
            raise HTTPException(
                status_code=503, detail="Discovery coordinator not available"
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise internal_server_error(
                logger, "Failed to get discovery status"
            ) from exc

    @router.post("/api/discovery/start")
    async def start_background_discovery(request: Request) -> dict[str, Any]:
        """Start background discovery process."""
        try:
            if not discovery_coordinator:
                raise HTTPException(
                    status_code=503, detail="Discovery coordinator not available"
                )

            mode = (await request.json()).get("mode", "quick")
            if mode not in ["full", "quick", "yaml_only"]:
                raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}")

            result = await discovery_coordinator.start_discovery(mode=mode)
            if result["success"]:
                return {
                    "success": True,
                    "message": f"Discovery started in {mode} mode",
                    "mode": mode,
                }
            raise _discovery_failure("Unable to start discovery", result.get("error"))
        except HTTPException:
            raise
        except Exception as exc:
            raise internal_server_error(logger, "Failed to start discovery") from exc

    @router.post("/api/discovery/stop")
    async def stop_background_discovery() -> dict[str, Any]:
        """Stop running background discovery."""
        try:
            if not discovery_coordinator:
                raise HTTPException(
                    status_code=503, detail="Discovery coordinator not available"
                )

            result = await discovery_coordinator.stop_discovery()
            if result["success"]:
                return {"success": True, "message": "Discovery stopped"}
            raise _discovery_failure("Unable to stop discovery", result.get("error"))
        except HTTPException:
            raise
        except Exception as exc:
            raise internal_server_error(logger, "Failed to stop discovery") from exc

    @router.get("/api/discovery/results", response_model=dict[str, Any])
    async def get_discovery_results() -> dict[str, Any]:
        """Get discovery results if available."""
        try:
            if not discovery_coordinator:
                raise HTTPException(
                    status_code=503, detail="Discovery coordinator not available"
                )

            result = await discovery_coordinator.get_results()
            if result["success"]:
                return result
            raise _discovery_failure(
                "Discovery results are not available", result.get("error"), 404
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise internal_server_error(
                logger, "Failed to get discovery results"
            ) from exc

    @router.post("/api/discovery/reset")
    async def reset_discovery_state() -> dict[str, Any]:
        """Reset discovery state to idle."""
        try:
            if not discovery_coordinator:
                raise HTTPException(
                    status_code=503, detail="Discovery coordinator not available"
                )

            result = await discovery_coordinator.reset_state()
            if result["success"]:
                return result
            raise _discovery_failure(
                "Unable to reset discovery state", result.get("error")
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise internal_server_error(
                logger, "Failed to reset discovery state"
            ) from exc

    return router
