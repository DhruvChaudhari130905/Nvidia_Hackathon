"""Content-addressed blob store (hash to bytes)."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import Optional


class FileStore:
    """Simple async file store with content-addressed storage."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = (root or Path.cwd() / ".mux" / "files").resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _resolve_path(self, path: str) -> Path:
        """Resolve and validate path is within root directory.

        Args:
            path: Relative path to resolve

        Returns:
            Resolved absolute path within root

        Raises:
            ValueError: If path attempts to escape root directory
        """
        # Normalize the path (resolve .. and .)
        requested_path = (self._root / path).resolve()

        # Ensure the resolved path is within root
        try:
            requested_path.relative_to(self._root)
        except ValueError:
            raise ValueError(f"Path traversal attempt detected: {path}")

        return requested_path

    async def write(self, path: str, content: str) -> str:
        """Write content to path. Returns content hash."""
        async with self._lock:
            full_path = self._resolve_path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def read(self, path: str) -> str:
        """Read content from path."""
        async with self._lock:
            full_path = self._resolve_path(path)
            if not full_path.exists():
                raise FileNotFoundError(f"File not found: {path}")
            return full_path.read_text(encoding="utf-8")

    async def delete(self, path: str) -> bool:
        """Delete file at path. Returns True if existed."""
        async with self._lock:
            full_path = self._resolve_path(path)
            if full_path.exists():
                full_path.unlink()
                return True
            return False

    async def clear(self) -> None:
        """Delete every file under this store's root (used when state is rebuilt)."""
        async with self._lock:
            if self._root.exists():
                shutil.rmtree(self._root)
            self._root.mkdir(parents=True, exist_ok=True)

    async def exists(self, path: str) -> bool:
        async with self._lock:
            full_path = self._resolve_path(path)
            return full_path.exists()