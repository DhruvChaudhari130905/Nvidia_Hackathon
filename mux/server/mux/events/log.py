"""Append events to Postgres and read them back from a seq."""

from __future__ import annotations

from typing import Protocol, Optional, List, cast
from mux.events.models import BaseEvent, CheckpointCreatedEvent, EventType
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from mux.db.session import get_sessionmaker
from mux.db.tables import Event
from mux.events.models import EventEnvelope, RoomId


class EventLog(Protocol):
    """Protocol for event log implementations (in-memory, PostgreSQL, etc.).

    Implement this protocol for any event log backend.
    """
    room_id: str

    async def append(self, event: BaseEvent) -> None: ...
    async def read_from(self, seq: int, limit: int = 100) -> List[BaseEvent]: ...
    async def get_latest(self, limit: int = 100) -> List[BaseEvent]: ...
    async def get_all(self, room_id: str) -> List[BaseEvent]: ...
    async def has_events(self, room_id: str) -> bool: ...
    async def get_latest_checkpoint(self, room_id: str) -> Optional[CheckpointCreatedEvent]: ...
    async def get_since(self, room_id: str, sequence: int) -> List[BaseEvent]: ...


class InMemoryEventLog:
    """In-memory event log implementation (for development/testing).

    Swap for PostgreSQL implementation in production by implementing the EventLog protocol.
    """

    def __init__(self, room_id: str) -> None:
        self.room_id = room_id
        self._events: List[BaseEvent] = []
        self._sequence = 0
        self._checkpoints: List[CheckpointCreatedEvent] = []

    async def append(self, event: BaseEvent) -> None:
        """Append an event to the log.

        The log is the single source of sequence numbers: every appended event gets
        the next contiguous sequence (1, 2, 3, ...), whatever value the caller set.
        This keeps sequences unique even when several components append, and keeps
        read_from()/get_since() index arithmetic valid.
        """
        self._sequence += 1
        event.sequence = self._sequence

        event.prev_event_id = self._events[-1].id if self._events else None
        self._events.append(event)

        # Track checkpoints separately for fast rehydration
        if event.type == EventType.CHECKPOINT_CREATED:
            self._checkpoints.append(cast(CheckpointCreatedEvent, event))

    async def read_from(self, seq: int, limit: int = 100) -> List[BaseEvent]:
        """Read events starting from sequence number."""
        if seq <= 0:
            return []
        idx = seq - 1
        if idx >= len(self._events):
            return []
        return self._events[idx:idx + limit]

    async def get_latest(self, limit: int = 100) -> List[BaseEvent]:
        """Get the most recent events."""
        if not self._events:
            return []
        start = max(0, len(self._events) - limit)
        return self._events[start:]

    # --- Methods needed by registry.py and actor.py ---

    async def get_all(self, room_id: str) -> List[BaseEvent]:
        """Get all events for a room (used for full replay)."""
        if room_id != self.room_id:
            return []
        return self._events.copy()

    async def has_events(self, room_id: str) -> bool:
        """Check if room has any persisted events."""
        return room_id == self.room_id and len(self._events) > 0

    async def get_latest_checkpoint(self, room_id: str) -> Optional[CheckpointCreatedEvent]:
        """Get the most recent checkpoint event for fast rehydration."""
        if room_id != self.room_id or not self._checkpoints:
            return None
        return self._checkpoints[-1]

    async def get_since(self, room_id: str, sequence: int) -> List[BaseEvent]:
        """Get all events after a given sequence number (for checkpoint delta replay)."""
        if room_id != self.room_id:
            return []
        # Events are 1-indexed by sequence
        idx = sequence
        if idx >= len(self._events):
            return []
        return self._events[idx:]

    def __len__(self) -> int:
        return len(self._events)

    def __repr__(self) -> str:
        return f"InMemoryEventLog(room_id={self.room_id!r}, events={len(self._events)})"


# Backward compatibility alias (remove when all callers updated)
EventLogImpl = InMemoryEventLog


# --- Postgres-backed event log (checkpoints, rewind, room files) ---

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
