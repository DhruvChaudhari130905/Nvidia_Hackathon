"""Start, look up, and stop room actors. Rehydrates an actor from the event log after a crash."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from mux.events.log import EventLog
from mux.rooms.actor import RoomActor, ActorConfig, create_room_actor
from mux.events.models import EventType

logger = logging.getLogger(__name__)

# Global registry instance
_registry: Optional["RoomRegistry"] = None

# Public registry reference (set after init_registry)
registry: Optional["RoomRegistry"] = None

# Per-room event log getter (set by main.py)
get_event_log: Optional[Callable[[str], EventLog]] = None


def get_registry() -> "RoomRegistry":
    """Get the global room registry instance."""
    global _registry
    if _registry is None:
        raise RuntimeError("Room registry not initialized. Call init_registry() first.")
    return _registry


async def init_registry(
    default_config: Optional[ActorConfig] = None,
    **callbacks,
) -> "RoomRegistry":
    """Initialize the global room registry."""
    global _registry, registry
    if _registry is not None:
        logger.warning("Registry already initialized, returning existing instance")
        return _registry
    _registry = RoomRegistry(default_config, **callbacks)
    registry = _registry
    logger.info("Global room registry initialized")
    return _registry


async def shutdown_registry() -> None:
    """Shutdown the global room registry."""
    global _registry, registry
    if _registry is not None:
        await _registry.shutdown_all()
        _registry = None
        registry = None
        logger.info("Global room registry shut down")


class RoomRegistry:
    """
    Manages the lifecycle of RoomActor instances.

    Provides:
    - Create/start new room actors
    - Look up existing actors by room_id
    - Stop and cleanup actors
    - Rehydrate actors from event log after crash/restart
    """

    def __init__(
        self,
        default_config: Optional[ActorConfig] = None,
        *,
        on_event: Optional[Callable] = None,
        on_sitting_ended: Optional[Callable] = None,
        on_budget_pause: Optional[Callable] = None,
        on_budget_resume: Optional[Callable] = None,
        on_budget_warning: Optional[Callable] = None,
        on_lock_expire: Optional[Callable] = None,
    ) -> None:
        self.default_config = default_config or ActorConfig()
        self._on_event = on_event
        self._on_sitting_ended = on_sitting_ended
        self._on_budget_pause = on_budget_pause
        self._on_budget_resume = on_budget_resume
        self._on_budget_warning = on_budget_warning
        self._on_lock_expire = on_lock_expire

        self._actors: dict[str, RoomActor] = {}
        self._lock = asyncio.Lock()

    def _get_event_log(self, room_id: str) -> EventLog:
        """Get the event log for a specific room."""
        if get_event_log is None:
            raise RuntimeError("Event log factory not initialized. Call init_registry() first.")
        return get_event_log(room_id)

    async def create_room(
        self,
        room_id: str,
        owner_id: str,
        config: Optional[ActorConfig] = None,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> RoomActor:
        """Create and start a new room actor. Records ROOM_CREATED (owner + metadata)."""
        async with self._lock:
            if room_id in self._actors:
                raise ValueError(f"Room {room_id!r} already exists")

            event_log = self._get_event_log(room_id)
            if await event_log.has_events(room_id):
                raise ValueError(f"Room {room_id!r} already exists")

            actor = await create_room_actor(
                room_id=room_id,
                owner_id=owner_id,
                event_log=event_log,
                config=config or self.default_config,
                on_event=self._on_event,
                on_sitting_ended=self._on_sitting_ended,
                on_budget_pause=self._on_budget_pause,
                on_budget_resume=self._on_budget_resume,
                on_budget_warning=self._on_budget_warning,
                on_lock_expire=self._on_lock_expire,
            )
            await actor.init_room(name or room_id, description)
            self._actors[room_id] = actor

            logger.info(f"Created room {room_id} with owner {owner_id}")
            return actor

    async def get_room_or_rehydrate(
        self,
        room_id: str,
        config: Optional[ActorConfig] = None,
    ) -> Optional[RoomActor]:
        """
        Return the active actor for a room, rehydrating it from the event log if needed.

        Returns None if the room was never created or has been closed. Rooms are never
        created implicitly, so a request for an unknown room id cannot claim ownership.
        """
        async with self._lock:
            if room_id in self._actors:
                return self._actors[room_id]

            event_log = self._get_event_log(room_id)
            if not await event_log.has_events(room_id):
                return None
            return await self._rehydrate_locked(room_id, config)

    async def _rehydrate_locked(
        self,
        room_id: str,
        config: Optional[ActorConfig] = None,
    ) -> Optional[RoomActor]:
        """Rehydrate a room actor from the event log. Caller must hold self._lock."""
        if room_id in self._actors:
            raise ValueError(f"Room {room_id!r} already active")

        event_log = self._get_event_log(room_id)
        events = await event_log.get_all(room_id)

        created = next((e for e in events if e.type == EventType.ROOM_CREATED), None)
        if created is None:
            logger.error(f"Room {room_id} has events but no ROOM_CREATED event; refusing to rehydrate")
            return None
        if any(e.type == EventType.ROOM_CLOSED for e in events):
            logger.info(f"Room {room_id} is closed; not rehydrating")
            return None

        actor = RoomActor(
            room_id=room_id,
            owner_id=created.created_by,
            event_log=event_log,
            config=config or self.default_config,
            on_event=self._on_event,
            on_sitting_ended=self._on_sitting_ended,
            on_budget_pause=self._on_budget_pause,
            on_budget_resume=self._on_budget_resume,
            on_budget_warning=self._on_budget_warning,
            on_lock_expire=self._on_lock_expire,
        )

        await actor.replay(events)
        await actor.start()
        self._actors[room_id] = actor
        logger.info(f"Rehydrated room {room_id} from {len(events)} events (owner: {actor.owner_id})")
        return actor

    async def get_room(self, room_id: str) -> Optional[RoomActor]:
        """Get an existing active room actor by ID."""
        async with self._lock:
            return self._actors.get(room_id)

    async def stop_room(self, room_id: str, reason: str = "stopped") -> bool:
        """Stop and remove a room actor."""
        async with self._lock:
            actor = self._actors.pop(room_id, None)
        if actor:
            await actor.stop(reason)
            logger.info(f"Stopped room {room_id}: {reason}")
            return True
        return False

    async def list_rooms(self) -> list[str]:
        """List all active room IDs."""
        async with self._lock:
            return list(self._actors.keys())

    async def rehydrate_room(
        self,
        room_id: str,
        config: Optional[ActorConfig] = None,
    ) -> Optional[RoomActor]:
        """Rehydrate a room actor from the event log (replays all events, then starts it)."""
        async with self._lock:
            return await self._rehydrate_locked(room_id, config)

    async def shutdown_all(self) -> None:
        """Stop all room actors."""
        async with self._lock:
            actors = list(self._actors.values())
            self._actors.clear()

        errors = []
        for actor in actors:
            try:
                await actor.stop("registry_shutdown")
            except Exception as e:
                errors.append((actor.room_id, e))
                logger.exception(f"Error stopping room {actor.room_id}")

        if errors:
            logger.error(f"Errors stopping {len(errors)} rooms: {errors}")
        else:
            logger.info(f"Stopped {len(actors)} rooms cleanly")

    async def start(self) -> None:
        """Start the registry (no-op, kept for API compatibility)."""
        logger.info("Room registry started")

    async def stop(self) -> None:
        """Stop the registry and all room actors."""
        await self.shutdown_all()
        logger.info("Room registry stopped")


async def create_room_registry(
    event_log: Optional[EventLog] = None,
    default_config: Optional[ActorConfig] = None,
    **callbacks,
) -> RoomRegistry:
    """Factory function to create a room registry."""
    return RoomRegistry(default_config, **callbacks)