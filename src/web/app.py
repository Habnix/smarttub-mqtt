from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.core.capability_detector import CapabilityDetector
from src.core.config_loader import AppConfig
from src.core.discovery_result_store import DiscoveryResultStore
from src.core.runtime_health import RuntimeHealth
from src.core.smarttub_client import SmartTubClient
from src.core.state_manager import StateManager
from src.core.state_models import StateSnapshot
from src.core.version import get_smarttub_mqtt_version
from src.web.auth import BasicAuthMiddleware
from src.web.capability_router import create_capability_router
from src.web.command_router import create_command_router
from src.web.discovery_router import create_discovery_router
from src.web.errors import internal_server_error
from src.web.event_hub import WebEventHub
from src.web.event_router import create_event_router
from src.web.page_router import create_page_router
from src.web.state_router import create_state_router

logger = logging.getLogger(__name__)
WEB_PACKAGE_DIR = Path(__file__).resolve().parent


class WebApp:
    """Web application for SmartTub monitoring and control."""

    def __init__(
        self,
        config: AppConfig,
        state_manager: StateManager,
        smarttub_client: SmartTubClient | None = None,
        capability_detector: CapabilityDetector | None = None,
        error_tracker: Any = None,
        progress_tracker: Any = None,
        discovery_coordinator: Any = None,
        command_manager: Any = None,
        discovery_result_store: DiscoveryResultStore | None = None,
        mqtt_broker: Any = None,
    ):
        self.config = config
        self.state_manager = state_manager
        self.smarttub_client = smarttub_client
        self.capability_detector = capability_detector
        self.error_tracker = error_tracker  # T058
        self.progress_tracker = progress_tracker  # T059
        self.discovery_coordinator = discovery_coordinator  # Background Discovery
        self.command_manager = command_manager
        self.discovery_result_store = discovery_result_store or DiscoveryResultStore()
        self.event_hub = WebEventHub()
        self.runtime_health = RuntimeHealth(
            config,
            state_manager,
            mqtt_broker=mqtt_broker,
            smarttub_client=smarttub_client,
            command_manager=command_manager,
        )
        self._connect_live_events()

        # Create lifespan context manager for graceful shutdown
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            yield
            # Shutdown - suppress CancelledError during shutdown
            logger.info("Web UI shutting down gracefully")

        self.app = FastAPI(
            title="SmartTub MQTT Bridge",
            description="Monitor and control SmartTub whirlpool via MQTT",
            version=get_smarttub_mqtt_version(),
            lifespan=lifespan,
        )

        # Add Basic Auth middleware if enabled (T056)
        if (
            config.web.auth_enabled
            and config.web.basic_auth_username
            and config.web.basic_auth_password
        ):
            auth_middleware = BasicAuthMiddleware(
                username=config.web.basic_auth_username,
                password=config.web.basic_auth_password,
            )
            self.app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)

        # Mount static files (only if directory exists and has content)
        static_dir = WEB_PACKAGE_DIR / "static"
        if static_dir.is_dir() and any(static_dir.iterdir()):
            self.app.mount(
                "/static", StaticFiles(directory=str(static_dir)), name="static"
            )

        # Setup templates
        self.templates = Jinja2Templates(directory=str(WEB_PACKAGE_DIR / "templates"))

        # Register routes
        self._setup_error_routes()
        self.app.include_router(
            create_state_router(self.state_manager, self.runtime_health)
        )
        self.app.include_router(
            create_capability_router(self.config, self.capability_detector)
        )
        self.app.include_router(
            create_page_router(
                self.config,
                self.state_manager,
                self.capability_detector,
                self.templates,
            )
        )
        self.app.include_router(
            create_command_router(
                self.smarttub_client,
                self.command_manager,
                self.discovery_result_store,
                self.config.smarttub.device_id,
                self.capability_detector,
            )
        )
        self.app.include_router(
            create_discovery_router(
                progress_tracker=self.progress_tracker,
                discovery_coordinator=self.discovery_coordinator,
            )
        )
        self.app.include_router(
            create_event_router(
                self.event_hub,
                self.state_manager,
                self.command_manager,
                self.discovery_coordinator,
            )
        )

    def _connect_live_events(self) -> None:
        async def publish_state(snapshot: StateSnapshot) -> None:
            await self.event_hub.publish("state", snapshot)

        if hasattr(self.state_manager, "subscribe"):
            self.state_manager.subscribe(publish_state)
        if self.command_manager is not None and hasattr(
            self.command_manager, "subscribe_transitions"
        ):

            def publish_command(_record: dict[str, Any]) -> None:
                history = self.command_manager.get_command_history()
                asyncio.create_task(
                    self.event_hub.publish(
                        "command", {"commands": history, "total": len(history)}
                    )
                )

            self.command_manager.subscribe_transitions(publish_command)
        discovery_state_manager = getattr(
            self.discovery_coordinator, "state_manager", None
        )
        if discovery_state_manager is not None and hasattr(
            discovery_state_manager, "subscribe"
        ):

            async def publish_discovery(state: Any) -> None:
                payload = state.to_dict()
                payload["success"] = True
                payload["is_running"] = payload["status"] == "running"
                await self.event_hub.publish("discovery", payload)

            discovery_state_manager.subscribe(publish_discovery)

    def _setup_error_routes(self) -> None:
        """Register error-tracker routes owned by the application composition root."""

        @self.app.get("/api/errors", response_model=dict[str, Any])
        async def get_errors() -> dict[str, Any]:
            """Get error tracking summary (T058)."""
            try:
                if self.error_tracker:
                    summary = self.error_tracker.get_error_summary()
                    subsystems = self.error_tracker.get_subsystem_status()

                    return {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "summary": summary,
                        "subsystems": subsystems,
                    }
                else:
                    return {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "summary": {
                            "total_errors": 0,
                            "critical_count": 0,
                            "error_count": 0,
                        },
                        "subsystems": {},
                        "error_tracker_available": False,
                    }
            except Exception as e:
                raise internal_server_error(logger, "Failed to get errors") from e

        @self.app.post("/api/errors/clear")
        async def clear_errors(request: Request) -> dict[str, Any]:
            """Clear tracked errors (T058)."""
            try:
                data = (
                    await request.json()
                    if request.headers.get("content-type") == "application/json"
                    else {}
                )
                category = data.get("category")

                if self.error_tracker:
                    # Import ErrorCategory if available
                    try:
                        from src.core.error_tracker import ErrorCategory

                        cat_filter = (
                            ErrorCategory[category.upper()] if category else None
                        )
                    except (ImportError, KeyError, AttributeError):
                        cat_filter = None

                    cleared = self.error_tracker.clear_errors(cat_filter)

                    return {
                        "status": "success",
                        "cleared_count": cleared,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                else:
                    raise HTTPException(
                        status_code=503, detail="Error tracker not available"
                    )

            except HTTPException:
                raise
            except Exception as e:
                raise internal_server_error(logger, "Failed to clear errors") from e


# Convenience function for creating the app
def create_app(
    config: AppConfig,
    state_manager: StateManager,
    smarttub_client: SmartTubClient | None = None,
    capability_detector: CapabilityDetector | None = None,
    error_tracker: Any = None,
    progress_tracker: Any = None,
    discovery_coordinator: Any = None,
    command_manager: Any = None,
    discovery_result_store: DiscoveryResultStore | None = None,
    mqtt_broker: Any = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    web_app = WebApp(
        config,
        state_manager,
        smarttub_client,
        capability_detector,
        error_tracker,
        progress_tracker,
        discovery_coordinator,
        command_manager,
        discovery_result_store,
        mqtt_broker,
    )
    return web_app.app
