"""Tests for the append-only event log (events/log.py)."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mux.db.tables import Room
from mux.events import log
from mux.events.models import EventEnvelope

TS = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


def ev(room_id: UUID, seq: int, type: str = "message.posted", payload: dict | None = None) -> EventEnvelope:
    return EventEnvelope(seq=seq, room_id=room_id, type=type, actor="user-1", ts=TS, payload=payload or {})


async def test_append_read_roundtrip(db_session: AsyncSession, room: UUID) -> None:
    sent = [ev(room, 1, "room.created"), ev(room, 2, payload={"text": "hi", "nested": {"n": [1, 2]}})]
    await log.append(room, sent, session=db_session)
    assert await log.read_all(room, session=db_session) == sent


async def test_read_since_is_exclusive_and_ordered(db_session: AsyncSession, room: UUID) -> None:
    await log.append(room, [ev(room, s) for s in (3, 1, 2, 5, 4)], session=db_session)
    assert [e.seq for e in await log.read_since(room, 2, session=db_session)] == [3, 4, 5]
    assert await log.read_since(room, 5, session=db_session) == []


async def test_max_seq(db_session: AsyncSession, room: UUID) -> None:
    assert await log.max_seq(room, session=db_session) == 0
    await log.append(room, [ev(room, 1), ev(room, 7)], session=db_session)
    assert await log.max_seq(room, session=db_session) == 7


async def test_rooms_are_isolated(db_session: AsyncSession, room: UUID) -> None:
    other = uuid4()
    db_session.add(Room(id=other, owner_id=uuid4(), title="other"))
    await db_session.flush()
    await log.append(room, [ev(room, 1)], session=db_session)
    await log.append(other, [ev(other, 1), ev(other, 2)], session=db_session)  # same seq in another room is fine
    assert [e.seq for e in await log.read_all(room, session=db_session)] == [1]
    assert await log.max_seq(other, session=db_session) == 2


async def test_duplicate_seq_raises(db_session: AsyncSession, room: UUID) -> None:
    await log.append(room, [ev(room, 1)], session=db_session)
    with pytest.raises(IntegrityError):
        await log.append(room, [ev(room, 1)], session=db_session)


async def test_wrong_room_rejected_before_writing(db_session: AsyncSession, room: UUID) -> None:
    with pytest.raises(ValueError):
        await log.append(room, [ev(room, 1), ev(uuid4(), 2)], session=db_session)
    assert await log.read_all(room, session=db_session) == []


async def test_unknown_room_violates_fk(db_session: AsyncSession, room: UUID) -> None:
    ghost = uuid4()
    with pytest.raises(IntegrityError):
        await log.append(ghost, [ev(ghost, 1)], session=db_session)
