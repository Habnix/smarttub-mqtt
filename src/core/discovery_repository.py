"""Single, atomic persistence boundary for discovery YAML documents."""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

DiscoveryDocument = dict[str, Any]
DocumentUpdater = Callable[[DiscoveryDocument], DiscoveryDocument | None]

_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[Path, threading.RLock] = {}
_DOCUMENT_CACHE: dict[Path, DiscoveryDocument] = {}


def default_discovery_path(filename: str = "discovered_items.yaml") -> Path:
    """Resolve one runtime path instead of searching multiple candidates."""
    container_dir = Path("/config")
    if container_dir.is_dir() and os.access(container_dir, os.R_OK | os.W_OK):
        return container_dir / filename
    return Path(__file__).resolve().parents[2] / "config" / filename


def _path_lock(path: Path) -> threading.RLock:
    resolved = path.resolve()
    with _LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(resolved, threading.RLock())


class DiscoveryRepository:
    """Read and atomically update one versioned YAML document."""

    SCHEMA_VERSION = 1

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_discovery_path()
        self._resolved_path = self.path.resolve()
        self._lock = _path_lock(self.path)

    def exists(self) -> bool:
        return self.path.is_file()

    def read(self) -> DiscoveryDocument:
        """Return a detached mapping; missing or empty files are empty documents."""
        with self._lock:
            if not self.path.exists():
                _DOCUMENT_CACHE[self._resolved_path] = {}
                return {}
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                raise TypeError(f"Discovery document {self.path} must be a mapping")
            document = dict(data)
            _DOCUMENT_CACHE[self._resolved_path] = deepcopy(document)
            return deepcopy(document)

    async def read_async(self) -> DiscoveryDocument:
        """Read outside the event loop while retaining the same path lock."""
        return await asyncio.to_thread(self.read)

    def write(self, document: DiscoveryDocument) -> Path:
        """Atomically replace the document after durable same-directory staging."""
        with self._lock:
            self._write_locked(document)
        return self.path

    async def write_async(self, document: DiscoveryDocument) -> Path:
        return await asyncio.to_thread(self.write, document)

    def update(self, updater: DocumentUpdater) -> Path:
        """Lock read-modify-write as one transaction to prevent lost updates."""
        with self._lock:
            document = self.read()
            updated = updater(document)
            if updated is None:
                self.path.unlink(missing_ok=True)
                _DOCUMENT_CACHE.pop(self._resolved_path, None)
            else:
                self._write_locked(updated)
        return self.path

    async def update_async(self, updater: DocumentUpdater) -> Path:
        return await asyncio.to_thread(self.update, updater)

    def delete(self) -> None:
        with self._lock:
            self.path.unlink(missing_ok=True)
            _DOCUMENT_CACHE.pop(self._resolved_path, None)

    async def delete_async(self) -> None:
        await asyncio.to_thread(self.delete)

    def discovered_items(self) -> dict[str, Any]:
        items = self.read().get("discovered_items", {})
        return dict(items) if isinstance(items, dict) else {}

    async def discovered_items_async(self) -> dict[str, Any]:
        document = await self.read_async()
        items = document.get("discovered_items", {})
        return dict(items) if isinstance(items, dict) else {}

    def cached_discovered_items(self) -> dict[str, Any]:
        """Return the latest in-process snapshot without filesystem access."""
        with self._lock:
            document = deepcopy(_DOCUMENT_CACHE.get(self._resolved_path, {}))
        items = document.get("discovered_items", {})
        return dict(items) if isinstance(items, dict) else {}

    def _write_locked(self, document: DiscoveryDocument) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(document)
        payload.setdefault("schema_version", self.SCHEMA_VERSION)
        serialized = yaml.safe_dump(payload, sort_keys=False)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            _DOCUMENT_CACHE[self._resolved_path] = deepcopy(payload)
        finally:
            temporary.unlink(missing_ok=True)
