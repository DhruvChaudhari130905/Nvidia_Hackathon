
"""One RoomActor per room, created, or opened from the database the first time it is asked for.

Actors live in this one server process. Each room's seqs need a single writer (DB1), so run one worker.
"""

import asyncio
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mux.agents.llm import LLM
from mux.db.session import get_sessionmaker
from mux.events.models import DomainRole
from mux.integrations.tavily import WebSearch
from mux.rooms.actor import RoomActor
from mux.rooms.coding import RoomCoder
from mux.rooms.coordination import RoomCoordinator
from mux.rooms.emitter import Publish
from mux.sandbox.client import SandboxClient
from mux.sandbox.runner import Runner


class RoomRegistry:
    """The rooms this process has open."""

    def __init__(
        self, publish: Publish, *, sessionmaker: async_sessionmaker[AsyncSession] | None = None,
        llm: LLM | None = None, search: Callable[[], WebSearch] | None = None,
        sandbox: SandboxClient | None = None, sandbox_image: str = "",
    ) -> None:
        self._publish = publish
        self._sessionmaker = sessionmaker
        self._llm = llm  # None: messages to the agent are stored but nobody answers them
        self._search = search  # makes one WebSearch per room (its cache is per room); None: no research
        self._sandbox = sandbox  # None: the coder cannot build or test
        self._sandbox_image = sandbox_image
        self._actors: dict[UUID, RoomActor] = {}
        self._coordinators: dict[UUID, RoomCoordinator] = {}
        self._coders: dict[UUID, RoomCoder] = {}
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
        self._keep(actor)
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
                    self._keep(actor)
            return actor

    def _keep(self, actor: RoomActor) -> None:
        """Remember the actor and start its background tick, coordinator and coder."""
        self._actors[actor.room_id] = actor
        actor.start()
        if self._llm is not None:
            search = self._search() if self._search is not None else None
            coordinator = RoomCoordinator(actor, self._llm, search)
            self._coordinators[actor.room_id] = coordinator
            coordinator.start()
            runner = Runner(self._sandbox, actor.get_blob, self._sandbox_image) if self._sandbox is not None else None
            coder = RoomCoder(actor, self._llm, runner=runner, search=search)
            self._coders[actor.room_id] = coder
            coder.start()
        
    def session(self) -> AsyncSession:
        """A new session on the registry's database, for reads that need no actor (the room list)."""
        return(self._sessionmaker or get_sessionmaker())()

    def open_rooms(self) -> list[UUID]:
        """Ids of the rooms with an actor in memory."""
        return list(self._actors)

    async def close(self) -> None:
        """Stop every coder, coordinator and actor background tick (app shutdown)."""
        for coder in self._coders.values():
            await coder.stop()
        self._coders.clear()
        for coordinator in self._coordinators.values():
            await coordinator.stop()
        self._coordinators.clear()
        for actor in self._actors.values():
            await actor.stop()
        self._actors.clear()


_registry: RoomRegistry | None = None


def init_registry(
    publish: Publish, *, sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    llm: LLM | None = None, search: Callable[[], WebSearch] | None = None,
    sandbox: SandboxClient | None = None, sandbox_image: str = "",
) -> RoomRegistry:
    """Create the process-wide registry (called once, in the app lifespan)."""
    global _registry
    _registry = RoomRegistry(
        publish, sessionmaker=sessionmaker, llm=llm, search=search, sandbox=sandbox, sandbox_image=sandbox_image
    )
    return _registry


def get_registry() -> RoomRegistry:
    """The process-wide registry."""
    if _registry is None:
        raise RuntimeError("the room registry is not started: call init_registry in the app lifespan")
    return _registry
