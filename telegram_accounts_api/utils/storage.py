from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .exceptions import StorageError


class JsonListStorage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def read(self) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._read_sync)

    async def write(self, payload: list[dict[str, Any]]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._write_sync, payload)

    def _read_sync(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"Failed to read JSON file: {self.path}") from exc
        if not isinstance(raw, list):
            raise StorageError(f"Expected a JSON list in {self.path}")
        return [item for item in raw if isinstance(item, dict)]

    def _write_sync(self, payload: list[dict[str, Any]]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise StorageError(f"Failed to write JSON file: {self.path}") from exc

