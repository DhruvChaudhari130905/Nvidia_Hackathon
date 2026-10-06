
"""One RoomActor per room, created, or opened from the database the first time it is asked for.

Actors live in this one server process. Each room's seqs need a single writer (DB1), so run one worker.
"""

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mux.events.models import DomainRole
from mux.rooms.actor import RoomActor
from mux.rooms.emitter import Publish
from mux.db.session import get_sessionmaker


class RoomRegistry:
    """The rooms this process has open."""

    def __init__(self, publish: Publish, *, sessionmaker: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._publish = publish
        self._sessionmaker = sessionmaker
        self._actors: dict[UUID, RoomActor] = {}
        # Two requests for an unopened room must get one actor: two would hand out the same seqs
        self._opening = asyncio.Lock()

    async def create(
        self, owner_id: UUID, title: str, *, description: str = "", domain_role: DomainRole | None = None
    ) -> RoomActor:
        """Create a room and keep its actor."""
        actor = await RoomActor.create(
            owner_id, title, self._publish,
            description=description, domain_role=domain_role, sessionmaker=self._sessionmaker,
        )
        self._actors[actor.room_id] = actor
        actor.start()
        return actor

    async def get(self, room_id: UUID) -> RoomActor | None:
        """The room's actor, opened from the database the first time. None if there is no such room."""
        actor = self._actors.get(room_id)
        if actor is not None:
            return actor
        async with self._opening:
            actor = self._actors.get(room_id)  # another request may have opened it while this one waited
            if actor is None:
                actor = await RoomActor.open(room_id, self._publish, sessionmaker=self._sessionmaker)
                if actor is not None:
                    self._actors[room_id] = actor
                    actor.start()
            return actor
        
    def session(self) -> AsyncSession:
        """A new session on the registry's database, for reads that need no actor (the room list)."""
        return(self._sessionmaker or get_sessionmaker())()

    def open_rooms(self) -> list[UUID]:
        """Ids of the rooms with an actor in memory."""
        return list(self._actors)

    async def close(self) -> None:
        """Stop every actor's background tick (app shutdown)."""
        for actor in self._actors.values():
            await actor.stop()
        self._actors.clear()


_registry: RoomRegistry | None = None


def init_registry(publish: Publish, *, sessionmaker: async_sessionmaker[AsyncSession] | None = None) -> RoomRegistry:
    """Create the process-wide registry (called once, in the app lifespan)."""
    global _registry
    _registry = RoomRegistry(publish, sessionmaker=sessionmaker)
    return _registry


def get_registry() -> RoomRegistry:
    """The process-wide registry."""
    if _registry is None:
        raise RuntimeError("the room registry is not started: call init_registry in the app lifespan")
    return _registry
