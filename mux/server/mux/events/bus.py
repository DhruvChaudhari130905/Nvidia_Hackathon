"""Fans new events out to the room's WebSocket connections."""

import json
import logging
from dataclasses import dataclass
from typing import Dict, Protocol, Set

logger = logging.getLogger(__name__)


class TextSocket(Protocol):
    """What the bus needs from a socket (FastAPI's WebSocket satisfies it)."""

    async def send_text(self, data: str) -> None: ...


@dataclass(eq=False)
class RoomConnection:
    """One client socket and the highest stored seq it has been sent.

    The actor broadcasts from background tasks, so an event can reach the bus after the same
    event went out in a connection's initial dump; `last_seq` drops those duplicates.
    """

    websocket: TextSocket
    last_seq: int = 0

    async def send_text(self, text: str) -> None:
        await self.websocket.send_text(text)


class EventBus:
    """Manages WebSocket connections per room and broadcasts envelopes to them."""

    def __init__(self) -> None:
        self._room_connections: Dict[str, Set[RoomConnection]] = {}

    def connect(self, room_id: str, websocket: TextSocket, last_seq: int = 0) -> RoomConnection:
        """Register a connection that has already been sent everything up to `last_seq`."""
        conn = RoomConnection(websocket, last_seq)
        self._room_connections.setdefault(room_id, set()).add(conn)
        logger.debug(f"WebSocket connected to room {room_id} ({len(self._room_connections[room_id])} total)")
        return conn

    def disconnect(self, room_id: str, conn: RoomConnection) -> None:
        """Remove a connection from a room."""
        if room_id in self._room_connections:
            self._room_connections[room_id].discard(conn)
            if not self._room_connections[room_id]:
                del self._room_connections[room_id]

    async def publish_envelope(self, room_id: str, envelope: dict) -> None:
        """Send a stored event's envelope to every connection that hasn't had its seq yet."""
        seq = envelope["seq"]
        text = json.dumps(envelope, default=str)
        for conn in list(self._room_connections.get(room_id, ())):
            if seq <= conn.last_seq:
                continue
            conn.last_seq = seq
            await self._send(room_id, conn, text)

    async def publish_json(self, room_id: str, message: dict) -> None:
        """Broadcast an unstored message (presence, ...) to every connection in a room."""
        text = json.dumps(message, default=str)
        for conn in list(self._room_connections.get(room_id, ())):
            await self._send(room_id, conn, text)

    async def _send(self, room_id: str, conn: RoomConnection, text: str) -> None:
        try:
            await conn.send_text(text)
        except Exception as e:
            logger.warning(f"Failed to send to WebSocket in room {room_id}: {e}")
            self.disconnect(room_id, conn)

    def connection_count(self) -> int:
        return sum(len(c) for c in self._room_connections.values())


event_bus = EventBus()
