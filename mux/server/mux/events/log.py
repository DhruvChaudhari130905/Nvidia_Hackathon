"""Append events to Postgres and read them back from a seq."""

from __future__ import annotations

from typing import Protocol, Optional, List
from mux.events.models import BaseEvent, CheckpointCreatedEvent, EventType


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
            self._checkpoints.append(event)

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