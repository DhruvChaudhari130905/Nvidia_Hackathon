"""Append events to Postgres and read them back from a seq."""
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mux.db.session import get_sessionmaker
from mux.db.tables import Event
from mux.events.models import EventEnvelope, RoomId

@asynccontextmanager
async def scoped(session: AsyncSession | None) -> AsyncIterator[AsyncSession]:
    """Use the caller's session (they commit), or open one that commits on success."""
    if session is not None:
        yield session
        return
    async with get_sessionmaker()() as own, own.begin():
        yield own


def _to_envelope(row: Event) -> EventEnvelope:
    return EventEnvelope(seq=row.seq, room_id=row.room_id, type=row.type, actor=row.actor_id,
                         ts=row.created_at, payload=row.payload)


async def append(room_id: RoomId, events: Sequence[EventEnvelope], *, session: AsyncSession | None = None) -> None:
    """Insert events. Seq comes from the room actor (DB1); a duplicate seq raises IntegrityError."""
    if any(e.room_id != room_id for e in events):
        raise ValueError("event room_id does not match room_id")
    async with scoped(session) as s:
        s.add_all(
            Event(room_id=e.room_id, seq=e.seq, type=e.type, actor_id=e.actor, payload=e.payload, created_at=e.ts)
            for e in events
        )
        await s.flush()


async def read_since(room_id: RoomId, seq: int, *, session: AsyncSession | None = None) -> list[EventEnvelope]:
    """Events with seq greater than `seq`, greyed ones included (DB7)."""
    async with scoped(session) as s:
        rows = await s.scalars(select(Event).where(Event.room_id == room_id, Event.seq > seq).order_by(Event.seq))
        return [_to_envelope(r) for r in rows]


async def read_all(room_id: RoomId, *, session: AsyncSession | None = None) -> list[EventEnvelope]:
    """Every event of the room in seq order."""
    return await read_since(room_id, 0, session=session)


async def max_seq(room_id: RoomId, *, session: AsyncSession | None = None) -> int:
    """Highest seq in the room, or 0 if empty (the actor resumes at this + 1)."""
    async with scoped(session) as s:
        return (await s.scalar(select(func.coalesce(func.max(Event.seq), 0)).where(Event.room_id == room_id))) or 0
