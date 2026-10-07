"""Jinja page routes for the SmartTub Web UI."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from src.core.capability_detector import CapabilityDetector
from src.core.config_loader import AppConfig
from src.core.state_manager import StateManager
from src.web.view_models import WebViewModels

logger = logging.getLogger(__name__)


def create_page_router(
    config: AppConfig,
    state_manager: StateManager,
    capability_detector: CapabilityDetector | None,
    templates: Jinja2Templates,
) -> APIRouter:
    """Create the rendered UI routes with their explicit collaborators."""
    router = APIRouter()
    view_models = WebViewModels(config, state_manager, capability_detector)

    def render_error(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"request": request, "config": config},
            status_code=500,
        )

    @router.get("/", response_class=HTMLResponse)
    async def overview(request: Request) -> HTMLResponse:
        """Render the main overview page."""
        try:
            return templates.TemplateResponse(
                request,
                "overview.html",
                {"request": request, **(await view_models.overview_context())},
            )
        except Exception:
            logger.exception("Failed to render the overview page")
            return render_error(request)

    @router.get("/discovery", response_class=HTMLResponse)
    async def discovery_page(request: Request) -> HTMLResponse:
        """Render the discovery page."""
        try:
            return templates.TemplateResponse(
                request, "discovery.html", {"request": request, "config": config}
            )
        except Exception:
            logger.exception("Failed to render the discovery page")
            return render_error(request)

    @router.get("/controls", response_class=HTMLResponse)
    async def controls(request: Request) -> HTMLResponse:
        """Render the controls page."""
        try:
            return templates.TemplateResponse(
                request,
                "controls.html",
                {"request": request, **(await view_models.controls_context())},
            )
        except Exception:
            logger.exception("Failed to render the controls page")
            return render_error(request)

    return router
