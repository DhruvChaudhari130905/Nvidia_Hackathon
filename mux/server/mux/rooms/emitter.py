"""Room event writer: gives each event the next seq, stores it, and broadcasts it after the transaction commits.

One Emitter per room. Seqs come only from here (DB1), so each room must have one writer: one server process.
Transactions on one Emitter run one at a time. Never open one inside another: it would wait forever.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mux.db.session import get_sessionmaker
from mux.events import log
from mux.events.models import EventEnvelope, RoomId

logger = logging.getLogger(__name__)

Publish = Callable[[EventEnvelope], Awaitable[None]]

class Batch:
    """Events written in one transaction. Use `session` for other writes that must commit with them."""

    def __init__(self, room_id: RoomId, first_seq: int, session: AsyncSession) -> None:
        self.session = session
        self.events: list[EventEnvelope] = []
        self._room_id = room_id
        self._next_seq = first_seq

    async def emit(self, type:str, payload: BaseModel | dict, actor: str) -> EventEnvelope:
        """Store one event in this transaction. It is broadcast after the commit."""
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        event = EventEnvelope(
            seq = self._next_seq, type=type, ts=datetime.now(UTC), room_id=self._room_id, actor=actor, payload=data,
        )
        await log.append(self._room_id, [event], session=self.session)
        self._next_seq += 1
        self.events.append(event)
        return event
    
class Emitter:
    """Writes a room's events: next seq, store, then broadcast in seq order."""

    def __init__(
            self,
            room_id: RoomId,
            last_seq: int,
            publish: Publish,
            *,
            sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.room_id = room_id
        self.seq = last_seq # highest commited seq
        self._publish = publish
        self.sessionmaker = sessionmaker or get_sessionmaker()
        self._lock = asyncio.Lock()

    @classmethod
    async def resume(
        cls, room_id: RoomId, publish: Publish, *, sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    ) -> "Emitter":
        """An Emitter that continues after the room's highest stored seq."""
        maker = sessionmaker or get_sessionmaker()
        async with maker() as s:
            last = await log.max_seq(room_id, session=s)
        return cls(room_id, last, publish, sessionmaker=maker)
    
    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Batch]:
        """A transaction for events and the writes that go with them. An exception inside stores nothing."""
        async with self._lock:
            async with self.sessionmaker() as s, s.begin():
                batch = Batch(self.room_id, self.seq + 1, s)
                yield batch
            #only reached after the commit succeded
            if batch.events:
                self.seq = batch.events[-1].seq
            for event in batch.events: #still under the lock, so broadcasts keep seq order
                await self._safe_publish(event)

    async def emit(self, type:str, payload: BaseModel | dict, actor: str) -> EventEnvelope:
        """One event in its own transaction."""
        async with self.transaction() as tx:
            return await tx.emit(type, payload, actor)
        
    async def _safe_publish(self, event: EventEnvelope) -> None:
        # The event is stored, so a client that missed it gets it back on reconnect with ?since
        try: 
            await self._publish(event)
        except Exception:
            logger.exception("Publishing event %s of room %s failed", event.seq, self.room_id)
