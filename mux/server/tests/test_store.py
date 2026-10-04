"""Tests for the content-addressed blob store (files/store.py)."""

from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mux.db.tables import Blob
from mux.files import store

# ---- pure ----


def test_normalize_crlf_and_cr_to_lf() -> None:
    assert store.normalize(b"a\r\nb\rc\n") == b"a\nb\nc\n"


def test_normalize_leaves_binary_alone() -> None:
    png = b"\x89PNG\r\n\x1a\n\x00\x00"
    assert store.normalize(png) == png  # has NUL bytes
    latin1 = b"caf\xe9\r\n"
    assert store.normalize(latin1) == latin1  # not UTF-8


def test_hash_is_sha256_hex() -> None:
    assert store.hash_bytes(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# ---- Postgres ----


async def test_put_get_roundtrip_normalised(db_session: AsyncSession, room: UUID) -> None:
    h = await store.put(b"one\r\ntwo\r\n", session=db_session)
    assert h == store.hash_bytes(b"one\ntwo\n")
    assert await store.get(h, session=db_session) == b"one\ntwo\n"


async def test_crlf_and_lf_share_one_blob(db_session: AsyncSession, room: UUID) -> None:
    h1 = await store.put(b"x\r\n", session=db_session)
    h2 = await store.put(b"x\n", session=db_session)
    assert h1 == h2
    assert await db_session.scalar(select(func.count()).select_from(Blob)) == 1


async def test_put_records_size(db_session: AsyncSession, room: UUID) -> None:
    h = await store.put(b"hello", session=db_session)
    assert await db_session.scalar(select(Blob.size).where(Blob.hash == h)) == 5


async def test_size_limit_is_after_normalising(db_session: AsyncSession, room: UUID) -> None:
    exact = b"a" * store.MAX_BLOB_BYTES
    await store.put(exact, session=db_session)
    # One byte over, but its CRLF shrinks to LF, so it fits.
    await store.put(b"a" * (store.MAX_BLOB_BYTES - 1) + b"\r\n", session=db_session)
    with pytest.raises(store.BlobTooLarge):
        await store.put(exact + b"a", session=db_session)


async def test_get_missing_raises_keyerror(db_session: AsyncSession, room: UUID) -> None:
    with pytest.raises(KeyError):
        await store.get("0" * 64, session=db_session)
