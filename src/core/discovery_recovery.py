"""Persistent recovery journal for hardware-mutating light discovery."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from src.core.discovery_repository import DiscoveryRepository, default_discovery_path


class DiscoveryRecoveryJournal:
    """Atomically persist the original state of lights currently under test."""

    def __init__(self, path: Path | None = None) -> None:
        self.repository = DiscoveryRepository(
            path or default_discovery_path("discovery_recovery.yaml")
        )
        self.path = self.repository.path

    def entries(self) -> list[dict[str, Any]]:
        data = self.repository.read()
        entries = data.get("pending", []) if isinstance(data, dict) else []
        return [dict(entry) for entry in entries if isinstance(entry, dict)]

    async def entries_async(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.entries)

    def record(self, spa_id: str, zone: int, original_state: dict[str, Any]) -> None:
        def update(data: dict[str, Any]) -> dict[str, Any]:
            entries = [
                dict(entry)
                for entry in data.get("pending", [])
                if isinstance(entry, dict)
                and not (
                    str(entry.get("spa_id")) == str(spa_id)
                    and entry.get("zone") == zone
                )
            ]
            entries.append(
                {
                    "spa_id": str(spa_id),
                    "zone": zone,
                    "original_state": dict(original_state),
                }
            )
            return {"version": 1, "pending": entries}

        self.repository.update(update)

    async def record_async(
        self, spa_id: str, zone: int, original_state: dict[str, Any]
    ) -> None:
        await asyncio.to_thread(self.record, spa_id, zone, original_state)

    def clear(self, spa_id: str, zone: int) -> None:
        def update(data: dict[str, Any]) -> dict[str, Any] | None:
            entries = [
                dict(entry)
                for entry in data.get("pending", [])
                if isinstance(entry, dict)
                and not (
                    str(entry.get("spa_id")) == str(spa_id)
                    and entry.get("zone") == zone
                )
            ]
            return {"version": 1, "pending": entries} if entries else None

        self.repository.update(update)

    async def clear_async(self, spa_id: str, zone: int) -> None:
        await asyncio.to_thread(self.clear, spa_id, zone)
