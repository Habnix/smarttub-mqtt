"""Bounded in-process fan-out for Server-Sent Events."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from copy import deepcopy
from typing import Any


class WebEventHub:
    """Fan out safe state changes without coupling core services to FastAPI."""

    def __init__(self, queue_size: int = 32) -> None:
        self._queue_size = queue_size
        self._subscribers: set[asyncio.Queue[tuple[str, dict[str, Any]]]] = set()

    def subscribe(self) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(
            maxsize=self._queue_size
        )
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[tuple[str, dict[str, Any]]]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: str, payload: Mapping[str, Any]) -> None:
        """Publish an isolated event, retaining the newest item for slow clients."""
        message = (event, deepcopy(dict(payload)))
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:  # pragma: no cover - race defensive
                    pass
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:  # pragma: no cover - race defensive
                continue
