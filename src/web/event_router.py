"""Server-Sent Event endpoint for live web updates."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import StreamingResponse

from src.core.state_manager import StateManager
from src.web.event_hub import WebEventHub


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def create_event_router(
    event_hub: WebEventHub,
    state_manager: StateManager,
    command_manager: Any = None,
    discovery_coordinator: Any = None,
) -> APIRouter:
    """Expose a reconnect-friendly stream with initial snapshots."""
    router = APIRouter(tags=["events"])

    @router.get("/api/events")
    async def event_stream(request: Request) -> StreamingResponse:
        queue = event_hub.subscribe()

        async def stream() -> AsyncIterator[str]:
            try:
                yield "retry: 1000\n\n"
                state = state_manager.get_latest_snapshot()
                yield _sse(
                    "state",
                    cast(
                        dict[str, Any],
                        state
                        if state is not None
                        else state_manager.get_safe_fallback_state(),
                    ),
                )
                if command_manager is not None and hasattr(
                    command_manager, "get_command_history"
                ):
                    history = command_manager.get_command_history()
                    yield _sse("command", {"commands": history, "total": len(history)})
                if discovery_coordinator is not None and hasattr(
                    discovery_coordinator, "get_status"
                ):
                    status = await discovery_coordinator.get_status()
                    if isinstance(status, dict):
                        yield _sse("discovery", status)
                while not await request.is_disconnected():
                    try:
                        event, payload = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        yield ": keepalive\n\n"
                    else:
                        yield _sse(event, payload)
            finally:
                event_hub.unsubscribe(queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
