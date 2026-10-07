"""Persistence boundary for background light-mode discovery results."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from src.core.discovery_repository import DiscoveryRepository

logger = logging.getLogger(__name__)


class DiscoveryResultStore:
    """Merge detected light modes into the persisted discovery document."""

    def __init__(self, path: Path | None = None) -> None:
        self.repository = DiscoveryRepository(path)
        self.path = self.repository.path

    def save_light_modes(
        self,
        results: dict[str, Any],
        run_metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Persist light-mode discoveries and optional last-run metadata."""

        def merge(existing_data: dict[str, Any]) -> dict[str, Any]:
            if not isinstance(existing_data.get("discovered_items"), dict):
                existing_data["discovered_items"] = {}

            for spa_id, spa_data in results["spas"].items():
                spa_entry = existing_data["discovered_items"].setdefault(spa_id, {})
                existing_lights = spa_entry.get("lights", [])
                for new_light in spa_data["lights"]:
                    existing_light = next(
                        (
                            light
                            for light in existing_lights
                            if light.get("id") == new_light["id"]
                        ),
                        None,
                    )
                    if existing_light is None:
                        light_entry = {
                            "id": new_light["id"],
                            "detected_modes": new_light["detected_modes"],
                        }
                        if "zone" in new_light:
                            light_entry["zone"] = new_light["zone"]
                        if "mode_results" in new_light:
                            light_entry["mode_results"] = new_light["mode_results"]
                        if "state_restored" in new_light:
                            light_entry["state_restored"] = new_light["state_restored"]
                        existing_lights.append(light_entry)
                    else:
                        existing_light["detected_modes"] = new_light["detected_modes"]
                        if "zone" in new_light:
                            existing_light["zone"] = new_light["zone"]
                        if "mode_results" in new_light:
                            existing_light["mode_results"] = new_light["mode_results"]
                        if "state_restored" in new_light:
                            existing_light["state_restored"] = new_light[
                                "state_restored"
                            ]
                spa_entry["lights"] = existing_lights

            if run_metadata is not None:
                discovery_data = existing_data.get("discovery", {})
                if not isinstance(discovery_data, dict):
                    discovery_data = {}
                discovery_data["last_run"] = dict(run_metadata)
                existing_data["discovery"] = discovery_data
            return existing_data

        self.repository.update(merge)
        logger.info("Discovery results merged and saved to %s", self.path)
        return self.path

    async def save_light_modes_async(
        self,
        results: dict[str, Any],
        run_metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Persist through a worker thread for event-loop callers."""
        return await asyncio.to_thread(self.save_light_modes, results, run_metadata)

    def load_last_run(self) -> dict[str, Any] | None:
        """Load the last persisted run and reconstruct WebUI result details."""
        data = self._load_existing_data()
        discovery = data.get("discovery", {})
        metadata = discovery.get("last_run") if isinstance(discovery, dict) else None
        if not isinstance(metadata, dict):
            return None

        spas: dict[str, Any] = {}
        for spa_id, spa_data in data["discovered_items"].items():
            if not isinstance(spa_data, dict):
                continue
            lights = spa_data.get("lights", [])
            if not isinstance(lights, list) or not lights:
                continue
            spas[str(spa_id)] = {
                "spa_id": str(spa_id),
                "lights": [dict(light) for light in lights if isinstance(light, dict)],
            }

        total_lights = sum(len(spa["lights"]) for spa in spas.values())
        total_modes = sum(
            len(light.get("detected_modes", []))
            for spa in spas.values()
            for light in spa["lights"]
        )
        return {
            **metadata,
            "results": {
                "spas": spas,
                "yaml_path": str(self.path),
                "total_lights": metadata.get("total_lights", total_lights),
                "total_modes_detected": metadata.get(
                    "total_modes_detected", total_modes
                ),
            },
        }

    async def load_last_run_async(self) -> dict[str, Any] | None:
        return await asyncio.to_thread(self.load_last_run)

    def get_detected_modes(self, spa_id: str, light_id: str) -> list[str]:
        """Return the modes proven for one light zone by discovery."""
        data = self._load_existing_data()
        spa_entry = data["discovered_items"].get(str(spa_id), {})
        for light in spa_entry.get("lights", []):
            if str(light.get("id")) != str(light_id):
                continue
            modes = light.get("detected_modes", [])
            if not isinstance(modes, list):
                return []
            return [str(mode).strip().upper() for mode in modes if str(mode).strip()]
        return []

    async def get_detected_modes_async(self, spa_id: str, light_id: str) -> list[str]:
        return await asyncio.to_thread(self.get_detected_modes, spa_id, light_id)

    def _load_existing_data(self) -> dict[str, Any]:
        try:
            data = self.repository.read()
            if isinstance(data, dict) and isinstance(
                data.get("discovered_items"), dict
            ):
                return data
        except Exception:
            logger.warning("Could not load existing discovery YAML", exc_info=True)
        return {"discovered_items": {}}
