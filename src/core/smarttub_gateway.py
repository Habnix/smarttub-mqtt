"""Central compatibility boundary for undocumented python-smarttub requests.

python-smarttub 0.0.48 exposes ``Spa.request`` but does not define it as a
stable high-level control API. Every use is kept here so an upstream upgrade
has one auditable compatibility boundary.
"""

from __future__ import annotations

import asyncio
from typing import Any


class SmartTubGateway:
    """Wrap low-level SmartTub requests used by bridge compatibility code."""

    TESTED_UPSTREAM_VERSION = "0.0.48"

    async def request(
        self,
        spa: Any,
        method: str,
        endpoint: str,
        body: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        """Execute one low-level request with optional local timeout."""
        operation = (
            spa.request(method, endpoint)
            if body is None
            else spa.request(method, endpoint, body)
        )
        if timeout is None:
            return await operation
        return await asyncio.wait_for(operation, timeout=timeout)

    async def get_raw_lights(self, spa: Any) -> list[dict[str, Any]]:
        """Return raw light dictionaries needed for RGB values missing upstream."""
        response = await self.request(spa, "GET", "lights")
        if not isinstance(response, dict):
            return []
        lights = response.get("lights", [])
        return lights if isinstance(lights, list) else []

    async def patch_light(
        self,
        spa: Any,
        zone: int,
        body: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> Any:
        """Patch one light zone through the centralized compatibility path."""
        return await self.request(spa, "PATCH", f"lights/{zone}", body, timeout=timeout)
