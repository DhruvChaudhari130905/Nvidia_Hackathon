"""Content-addressed blob store (hash to bytes)."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import Optional
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from mux.db.tables import Blob
from mux.events.log import scoped


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


# --- Postgres-backed blob store (checkpoints, rewind, room files, coder tools) ---

MAX_BLOB_BYTES = 1_048_576


class BlobTooLarge(ValueError):
    """Raised when a blob exceeds `MAX_BLOB_BYTES` (DB10)."""


def normalize(data: bytes) -> bytes:
    """Convert CRLF and CR to LF, but only for UTF-8 text with no NUL bytes (DB10, R8). Binary is untouched."""
    if b"\x00" in data:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def hash_bytes(data: bytes) -> str:
    """sha256 hex digest."""
    return hashlib.sha256(data).hexdigest()


async def put(data: bytes, *, session: AsyncSession | None = None) -> str:
    """Store the normalized bytes (once) and return their hash."""
    data = normalize(data)
    if len(data) > MAX_BLOB_BYTES:
        raise BlobTooLarge(f"{len(data)} bytes exceeds {MAX_BLOB_BYTES}")
    h = hash_bytes(data)
    async with scoped(session) as s:
        await s.execute(insert(Blob).values(hash=h, content=data, size=len(data)).on_conflict_do_nothing())
    return h


async def get(hash: str, *, session: AsyncSession | None = None) -> bytes:
    """Return the blob's bytes; raises KeyError if absent."""
    async with scoped(session) as s:
        content = await s.scalar(select(Blob.content).where(Blob.hash == hash))
    if content is None:
        raise KeyError(hash)
    return content
