
"""Fans events out to the WebSocket connections of each room."""

import logging
from typing import Protocol
from uuid import UUID

from mux.events.models import EventEnvelope

logger = logging.getLogger(__name__)

class Socket(Protocol):
    """What the bus needs from a connection. FastAPI's WebSocket has it; tests use a fake."""

    async def send_text(self, data: str) -> None: ...

class EventBus:
    """The open connections of each room, and broadcasting to them."""

    def __init__(self) -> None:
        self._rooms: dict[UUID, set[Socket]] = {}

    def connect(self, room_id: UUID, socket: Socket) -> None:
        self._rooms.setdefault(room_id, set()).add(socket)

    def disconnect(self, room_id: UUID, socket: Socket) -> None:
        sockets = self._rooms.get(room_id)
        if sockets is None:
            return
        sockets.discard(socket)
        if not sockets:
            del self._rooms[room_id]

    async def publish(self, event: EventEnvelope) -> None:
        """Send a stored event to everyone in its room (the Emitter's publish callback)."""
        await self.send(event.room_id, event.model_dump_json())

    async def send(self, room_id: UUID, text: str) -> None:
        """Send text to every connection in the room. A connection that fails is dropped."""
        for socket in list(self._rooms.get(room_id, ())):
            try: 
                await socket.send_text(text)
            except Exception:
                logger.warning("Dropping a dead WebSocket in room %s", room_id, exc_info=True)
                self.disconnect(room_id, socket)

    def connection_count(self, room_id: UUID | None = None) -> int:
        """Connections in one room, or in all rooms."""
        if room_id is not None:
            return len(self._rooms.get(room_id, ()))
        return sum(len(sockets) for sockets in self._rooms.values())
    

event_bus = EventBus()
        