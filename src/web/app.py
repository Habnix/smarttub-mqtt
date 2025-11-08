from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.capability_detector import CapabilityDetector
from src.web.auth import BasicAuthMiddleware


class WebApp:
    """Web application for SmartTub monitoring and control."""

    def __init__(
        self, 
        config: AppConfig, 
        state_manager: StateManager, 
        smarttub_client: SmartTubClient = None, 
        capability_detector: CapabilityDetector = None,
        error_tracker: Any = None,
        progress_tracker: Any = None
    ):
        self.config = config
        self.state_manager = state_manager
        self.smarttub_client = smarttub_client
        self.capability_detector = capability_detector
        self.error_tracker = error_tracker  # T058
        self.progress_tracker = progress_tracker  # T059
        self.app = FastAPI(
            title="SmartTub MQTT Bridge",
            description="Monitor and control SmartTub whirlpool via MQTT",
            version="1.0.0"
        )

        # Add Basic Auth middleware if enabled (T056)
        if config.web.auth_enabled:
            if config.web.basic_auth_username and config.web.basic_auth_password:
                auth_middleware = BasicAuthMiddleware(
                    username=config.web.basic_auth_username,
                    password=config.web.basic_auth_password
                )
                self.app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)

        # Mount static files (only if directory exists and has content)
        import os
        static_dir = "src/web/static"
        if os.path.exists(static_dir) and os.path.isdir(static_dir):
            # Check if directory has any files
            if any(os.scandir(static_dir)):
                self.app.mount("/static", StaticFiles(directory=static_dir), name="static")

        # Setup templates
        self.templates = Jinja2Templates(directory="src/web/templates")

        # Register routes
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup API and UI routes."""

        @self.app.get("/api/state", response_model=Dict[str, Any])
        async def get_state() -> Dict[str, Any]:
            """Get current SmartTub state snapshot."""
            try:
                # Get current state from state manager
                snapshot = self.state_manager._last_snapshot
                if snapshot is None:
                    # Return safe fallback if no state available
                    return self.state_manager.get_safe_fallback_state()

                return snapshot
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to get state: {str(e)}")

        @self.app.get("/api/capabilities", response_model=Dict[str, Any])
        async def get_capabilities() -> Dict[str, Any]:
            """Get SmartTub capabilities and supported features."""
            try:
                if self.capability_detector:
                    # Get all known spas and their capabilities
                    spas_capabilities = {}
                    for spa_id in list(self.capability_detector._capabilities_cache.keys()):
                        capability_profile = self.capability_detector.get_capability_profile(spa_id)
                        spas_capabilities[spa_id] = capability_profile

                    return {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "spas": spas_capabilities,
                        "mqtt_topics": {
                            "base_topic": self.config.mqtt.base_topic,
                            "capability_meta_topics": [
                                f"{self.config.mqtt.base_topic}/spa/{{spa_id}}/capability/meta"
                                for spa_id in spas_capabilities.keys()
                            ]
                        }
                    }
                else:
                    # Fallback to static capabilities if detector not available
                    return {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "spas": {},
                        "mqtt_topics": {
                            "base_topic": self.config.mqtt.base_topic,
                            "capability_meta_topics": []
                        },
                        "note": "Capability detector not available - showing static capabilities"
                    }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to get capabilities: {str(e)}")

        @self.app.get("/", response_class=HTMLResponse)
        async def overview(request: Request) -> HTMLResponse:
            """Render main overview page."""
            try:
                # Get current state for template
                current_state = self.state_manager._last_snapshot
                if current_state is None:
                    current_state = self.state_manager.get_safe_fallback_state()

                # Get capabilities for template
                capabilities = {}
                if self.capability_detector:
                    for spa_id in list(self.capability_detector._capabilities_cache.keys()):
                        capabilities[spa_id] = self.capability_detector.get_capability_profile(spa_id)

                return self.templates.TemplateResponse(
                    "overview.html",
                    {
                        "request": request,
                        "state": current_state,
                        "capabilities": capabilities,
                        "config": self.config,
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                )
            except Exception as e:
                # Fallback to error page
                return self.templates.TemplateResponse(
                    "error.html",
                    {
                        "request": request,
                        "error": str(e)
                    }
                )

        @self.app.get("/health")
        async def health_check() -> Dict[str, str]:
            """Health check endpoint."""
            return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

        @self.app.get("/api/errors", response_model=Dict[str, Any])
        async def get_errors() -> Dict[str, Any]:
            """Get error tracking summary (T058)."""
            try:
                if self.error_tracker:
                    summary = self.error_tracker.get_error_summary()
                    subsystems = self.error_tracker.get_subsystem_status()
                    
                    return {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "summary": summary,
                        "subsystems": subsystems
                    }
                else:
                    return {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "summary": {"total_errors": 0, "critical_count": 0, "error_count": 0},
                        "subsystems": {},
                        "error_tracker_available": False
                    }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to get errors: {str(e)}")

        @self.app.post("/api/errors/clear")
        async def clear_errors(request: Request) -> Dict[str, Any]:
            """Clear tracked errors (T058)."""
            try:
                data = await request.json() if request.headers.get("content-type") == "application/json" else {}
                category = data.get("category")
                
                if self.error_tracker:
                    # Import ErrorCategory if available
                    try:
                        from src.core.error_tracker import ErrorCategory
                        cat_filter = ErrorCategory[category.upper()] if category else None
                    except (ImportError, KeyError, AttributeError):
                        cat_filter = None
                    
                    cleared = self.error_tracker.clear_errors(cat_filter)
                    
                    return {
                        "status": "success",
                        "cleared_count": cleared,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                else:
                    raise HTTPException(status_code=503, detail="Error tracker not available")
            
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to clear errors: {str(e)}")

        @self.app.get("/api/discovery/progress", response_model=Dict[str, Any])
        async def get_discovery_progress() -> Dict[str, Any]:
            """Get discovery progress status (T059)."""
            try:
                if self.progress_tracker:
                    progress = self.progress_tracker.get_progress()
                    
                    return {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "progress": progress,
                        "available": True
                    }
                else:
                    return {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "progress": {},
                        "available": False,
                        "message": "Progress tracker not available"
                    }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to get discovery progress: {str(e)}")

        @self.app.get("/api/discovery/progress/{spa_id}", response_model=Dict[str, Any])
        async def get_spa_progress(spa_id: str) -> Dict[str, Any]:
            """Get discovery progress for a specific spa (T059)."""
            try:
                if self.progress_tracker:
                    spa_progress = self.progress_tracker.get_spa_progress(spa_id)
                    
                    if spa_progress:
                        return {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "spa_progress": spa_progress,
                            "available": True
                        }
                    else:
                        raise HTTPException(status_code=404, detail=f"Spa {spa_id} not found in progress tracker")
                else:
                    raise HTTPException(status_code=503, detail="Progress tracker not available")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to get spa progress: {str(e)}")

        # Command endpoints
        @self.app.post("/api/commands/set_temperature")
        async def set_temperature(request: Request) -> Dict[str, Any]:
            """Set spa target temperature."""
            try:
                data = await request.json()
                temperature = data.get("temperature")

                if temperature is None:
                    raise HTTPException(status_code=400, detail="Temperature value required")

                if self.smarttub_client:
                    await self.smarttub_client.set_temperature(float(temperature))
                    return {
                        "status": "success",
                        "message": f"Temperature set to {temperature}°C",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                else:
                    raise HTTPException(status_code=503, detail="SmartTub client not available")

            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid temperature value: {str(e)}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to set temperature: {str(e)}")

        @self.app.post("/api/commands/set_heat_mode")
        async def set_heat_mode(request: Request) -> Dict[str, Any]:
            """Set spa heating mode."""
            try:
                data = await request.json()
                mode = data.get("mode")

                if mode is None:
                    raise HTTPException(status_code=400, detail="Mode value required")

                if self.smarttub_client:
                    await self.smarttub_client.set_heat_mode(str(mode))
                    return {
                        "status": "success",
                        "message": f"Heat mode set to {mode}",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                else:
                    raise HTTPException(status_code=503, detail="SmartTub client not available")

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to set heat mode: {str(e)}")

        @self.app.post("/api/commands/set_pump_state")
        async def set_pump_state(request: Request) -> Dict[str, Any]:
            """Set pump state."""
            try:
                data = await request.json()
                state = data.get("state")

                if state is None:
                    raise HTTPException(status_code=400, detail="State value required")

                if self.smarttub_client:
                    enabled = state.lower() == "on"
                    await self.smarttub_client.set_pump_state(enabled)
                    return {
                        "status": "success",
                        "message": f"Pump {'started' if enabled else 'stopped'}",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                else:
                    raise HTTPException(status_code=503, detail="SmartTub client not available")

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to set pump state: {str(e)}")

        @self.app.post("/api/commands/set_light_state")
        async def set_light_state(request: Request) -> Dict[str, Any]:
            """Set light state."""
            try:
                data = await request.json()
                state = data.get("state")

                if state is None:
                    raise HTTPException(status_code=400, detail="State value required")

                if self.smarttub_client:
                    enabled = state.lower() == "on"
                    await self.smarttub_client.set_light_state(enabled)
                    return {
                        "status": "success",
                        "message": f"Light {'turned on' if enabled else 'turned off'}",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                else:
                    raise HTTPException(status_code=503, detail="SmartTub client not available")

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to set light state: {str(e)}")

        @self.app.post("/api/commands/set_light_color")
        async def set_light_color(request: Request) -> Dict[str, Any]:
            """Set light color."""
            try:
                data = await request.json()
                color = data.get("color")

                if color is None:
                    raise HTTPException(status_code=400, detail="Color value required")

                if self.smarttub_client:
                    await self.smarttub_client.set_light_color(str(color))
                    return {
                        "status": "success",
                        "message": f"Light color set to {color}",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                else:
                    raise HTTPException(status_code=503, detail="SmartTub client not available")

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to set light color: {str(e)}")

        @self.app.post("/api/commands/set_light_brightness")
        async def set_light_brightness(request: Request) -> Dict[str, Any]:
            """Set light brightness."""
            try:
                data = await request.json()
                brightness = data.get("brightness")

                if brightness is None:
                    raise HTTPException(status_code=400, detail="Brightness value required")

                if self.smarttub_client:
                    await self.smarttub_client.set_light_brightness(int(brightness))
                    return {
                        "status": "success",
                        "message": f"Light brightness set to {brightness}%",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                else:
                    raise HTTPException(status_code=503, detail="SmartTub client not available")

            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid brightness value: {str(e)}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to set light brightness: {str(e)}")

        @self.app.get("/api/commands/history")
        async def get_command_history() -> Dict[str, Any]:
            """Get recent command history."""
            # For now, return a placeholder. In a full implementation,
            # this would return actual command history from a database or log
            return {
                "commands": [
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "command": "system_startup",
                        "status": "success",
                        "message": "System initialized"
                    }
                ],
                "total": 1
            }

        @self.app.get("/controls", response_class=HTMLResponse)
        async def controls(request: Request) -> HTMLResponse:
            """Render controls page."""
            try:
                # Get capabilities for template
                capabilities = {}
                if self.capability_detector:
                    for spa_id in list(self.capability_detector._capabilities_cache.keys()):
                        capabilities[spa_id] = self.capability_detector.get_capability_profile(spa_id)

                return self.templates.TemplateResponse(
                    "controls.html",
                    {
                        "request": request,
                        "capabilities": capabilities,
                        "config": self.config
                    }
                )
            except Exception as e:
                return self.templates.TemplateResponse(
                    "error.html",
                    {
                        "request": request,
                        "error": str(e)
                    }
                )


# Convenience function for creating the app
def create_app(
    config: AppConfig, 
    state_manager: StateManager, 
    smarttub_client: SmartTubClient = None, 
    capability_detector: CapabilityDetector = None,
    error_tracker: Any = None,
    progress_tracker: Any = None
) -> FastAPI:
    """Create and configure the FastAPI application."""
    web_app = WebApp(
        config, 
        state_manager, 
        smarttub_client, 
        capability_detector, 
        error_tracker,
        progress_tracker
    )
    return web_app.app