"""Fans new events out to the room's WebSocket connections."""

import json
import logging
from typing import Dict, Set
from fastapi import WebSocket
from mux.events.models import BaseEvent

logger = logging.getLogger(__name__)


class EventBus:
    """Manages WebSocket connections per room and broadcasts events to them."""

    def __init__(self) -> None:
        self._room_connections: Dict[str, Set[WebSocket]] = {}

    def connect(self, room_id: str, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection for a room."""
        if room_id not in self._room_connections:
            self._room_connections[room_id] = set()
        self._room_connections[room_id].add(websocket)
        logger.debug(
            f"WebSocket connected to room {room_id}. "
            f"Total connections for room: {len(self._room_connections[room_id])}"
        )

    def disconnect(self, room_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from a room."""
        if room_id in self._room_connections:
            self._room_connections[room_id].discard(websocket)
            logger.debug(
                f"WebSocket disconnected from room {room_id}. "
                f"Remaining connections: {len(self._room_connections[room_id])}"
            )
            if not self._room_connections[room_id]:
                del self._room_connections[room_id]

    async def publish(self, room_id: str, event: BaseEvent) -> None:
        """
        Publish an event to all WebSocket connections in a room.

        Args:
            room_id: The room to broadcast the event to.
            event: The event to broadcast (must be a BaseEvent instance).
        """
        if room_id not in self._room_connections:
            logger.debug(f"No WebSocket connections for room {room_id} to publish event {event.type}")
            return

        try:
            event_json = event.model_dump_json()
        except Exception as e:
            logger.error(f"Failed to serialize event {event.type}: {e}")
            return

        await self.publish_text(room_id, event_json)
        logger.debug(f"Published event {event.type} to room {room_id}")

    async def publish_json(self, room_id: str, message: dict) -> None:
        """Broadcast an arbitrary JSON-serializable message to a room."""
        await self.publish_text(room_id, json.dumps(message, default=str))

    async def publish_text(self, room_id: str, text: str) -> None:
        """Send raw text to every connection in a room, dropping dead connections."""
        # Iterate over a snapshot: connections may join/leave while we await sends
        connections = list(self._room_connections.get(room_id, ()))
        disconnected: Set[WebSocket] = set()
        for websocket in connections:
            try:
                await websocket.send_text(text)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket in room {room_id}: {e}")
                disconnected.add(websocket)

        for websocket in disconnected:
            self.disconnect(room_id, websocket)

    def connection_count(self) -> int:
        return sum(len(c) for c in self._room_connections.values())


event_bus = EventBus()