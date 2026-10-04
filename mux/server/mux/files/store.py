"""Content-addressed blob store (hash to bytes)."""

import hashlib

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mux.db.tables import Blob
from mux.events.log import scoped

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
