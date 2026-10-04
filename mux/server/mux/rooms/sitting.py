"""Detects the end of a sitting (all members gone for 30 min, or the owner clicks End session) and triggers the day log."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional, TypedDict
from uuid import uuid4
from datetime import datetime, timezone

from mux.events.log import EventLog
from mux.events.models import SittingEndedEvent, EventType

logger = logging.getLogger(__name__)


VALID_END_REASONS = frozenset({"idle_timeout", "owner_ended"})


class SittingStatus(TypedDict, total=False):
    """Typed sitting status for external consumers."""
    active: bool
    idle_seconds: Optional[float]
    member_count: int
    owner_id: str
    room_id: str


@dataclass(frozen=True, slots=True)
class SittingConfig:
    """Configuration for sitting detection."""
    idle_timeout: int = 1800  # 30 minutes in seconds
    check_interval: int = 60  # How often to check for idle sittings


class SittingManager:
    """
    Manages sitting lifecycle for a room.

    A sitting ends when:
    1. All active members have been idle for `idle_timeout` seconds (default 30 min)
    2. The room owner explicitly ends the session

    When a sitting ends, a SittingEndedEvent is emitted to the event log,
    which triggers day log generation.
    """

    def __init__(
        self,
        room_id: str,
        event_log: EventLog,
        owner_id: str,
        config: Optional[SittingConfig] = None,
        *,
        on_sitting_ended: Optional[Callable[[str, SittingEndedEvent], None]] = None,
    ) -> None:
        self.room_id = room_id
        self.event_log = event_log
        self.owner_id = owner_id
        self.config = config or SittingConfig()
        self._on_sitting_ended = on_sitting_ended

        self._active = True
        self._member_last_seen: dict[str, float] = {}  # user_id -> last activity timestamp
        self._active_members: set[str] = set()         # currently present members
        self._owner_ended = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the sitting monitor."""
        async with self._lock:
            if self._monitor_task is None:
                self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the sitting monitor."""
        async with self._lock:
            if self._monitor_task:
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
                self._monitor_task = None

    async def record_activity(self, user_id: str) -> None:
        """Record that a user is active in the room.
        If the owner rejoins after ending, allow a new sitting.
        """
        async with self._lock:
            if not self._active:
                # Owner rejoining after end_session starts a new sitting
                if user_id == self.owner_id and self._owner_ended:
                    self._active = True
                    self._owner_ended = False
                    self._member_last_seen.clear()
                    self._active_members.clear()
                    if self._monitor_task is None:
                        self._monitor_task = asyncio.create_task(self._monitor_loop())
                else:
                    return
            self._member_last_seen[user_id] = time.monotonic()
            self._active_members.add(user_id)

    async def record_leave(self, user_id: str) -> None:
        """Record that a user left the room."""
        async with self._lock:
            self._active_members.discard(user_id)
            # Keep last_seen for potential rejoining, but don't count in idle check

    async def end_session(self, user_id: str) -> bool:
        """
        Explicitly end the sitting (owner only).
        Returns True if sitting was ended, False if not owner or already ended.
        """
        fire_callback = None
        async with self._lock:
            if not self._active:
                return False
            if user_id != self.owner_id:
                return False

            self._owner_ended = True
            fire_callback = await self._end_sitting(reason="owner_ended")
            return True
        if fire_callback:
            fire_callback()
        return True

    # --- Public method expected by registry.py ---

    async def end(self) -> Callable[[], None] | None:
        """Public end method (called during rehydration for SITTING_ENDED events)."""
        return await self._end_sitting(reason="idle_timeout")

    def is_active(self) -> bool:
        """Check if sitting is still active."""
        return self._active

    async def get_idle_time(self) -> Optional[float]:
        """Get seconds since last member activity among active members, or None if no active members."""
        async with self._lock:
            if not self._active_members:
                return None
            now = time.monotonic()
            latest = max(
                self._member_last_seen.get(uid, 0)
                for uid in self._active_members
            )
            return now - latest

    async def get_status(self) -> SittingStatus:
        """Get current sitting status (typed)."""
        async with self._lock:
            idle = None
            if self._active_members:
                now = time.monotonic()
                latest = max(
                    self._member_last_seen.get(uid, 0)
                    for uid in self._active_members
                )
                idle = now - latest
            return SittingStatus(
                active=self._active,
                idle_seconds=idle,
                member_count=len(self._active_members),
                owner_id=self.owner_id,
                room_id=self.room_id,
            )

    async def _monitor_loop(self) -> None:
        """Background task that checks for idle sittings."""
        try:
            while self._active:
                await asyncio.sleep(self.config.check_interval)
                await self._check_idle()
        except asyncio.CancelledError:
            logger.debug("Sitting monitor cancelled for room %s", self.room_id)
            raise
        except Exception:
            logger.exception("Sitting monitor error for room %s", self.room_id)

    async def _check_idle(self) -> None:
        """Check if all active members have been idle long enough."""
        # Snapshot under lock, then evaluate without holding it
        async with self._lock:
            if not self._active or self._owner_ended:
                return
            if not self._active_members:
                return
            # Snapshot last_seen for active members only
            active_last_seen = {
                uid: self._member_last_seen.get(uid, 0)
                for uid in self._active_members
            }

        now = time.monotonic()
        all_idle = all(
            (now - last_seen) > self.config.idle_timeout
            for last_seen in active_last_seen.values()
        )

        if all_idle:
            fire_callback = await self._end_sitting(reason="idle_timeout")
            if fire_callback:
                fire_callback()

    async def _end_sitting(self, reason: str) -> Callable[[], None] | None:
        """End the sitting and emit event. Returns callback to fire after lock released."""
        if not self._active:
            return None

        if reason not in VALID_END_REASONS:
            raise ValueError(f"Invalid end reason: {reason!r}. Allowed: {VALID_END_REASONS}")

        self._active = False

        # Calculate sitting duration based on active members' activity
        if self._active_members:
            started_at = min(
                self._member_last_seen.get(uid, time.monotonic())
                for uid in self._active_members
            )
            ended_at = time.monotonic()
            duration_seconds = ended_at - started_at
        else:
            started_at = ended_at = time.monotonic()
            duration_seconds = 0.0

        # Get previous event ID for chain integrity
        prev_event_id = None
        try:
            recent = await self.event_log.get_latest(limit=1)
            if recent:
                prev_event_id = recent[0].id
        except Exception:
            logger.warning("Could not fetch previous event for room %s", self.room_id)

        event = SittingEndedEvent(
            id=uuid4(),
            type=EventType.SITTING_ENDED,
            room_id=self.room_id,
            user_id=self.owner_id if reason == "owner_ended" else None,
            timestamp=datetime.now(timezone.utc),
            sequence=0,  # EventLog will assign sequence
            prev_event_id=prev_event_id,
            reason=reason,
            duration_seconds=duration_seconds,
            participant_count=len(self._active_members),
        )

        # Emit to event log
        await self.event_log.append(event)

        # Stop monitoring
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None

        # Return callback to fire after lock released
        if self._on_sitting_ended:
            callback = self._on_sitting_ended
            def _fire():
                try:
                    callback(self.room_id, event)
                except Exception:
                    logger.exception("on_sitting_ended callback failed")
            return _fire
        return None

    @property
    def member_count(self) -> int:
        """Number of active members."""
        return len(self._active_members)

    def __repr__(self) -> str:
        return f"SittingManager(room_id={self.room_id!r}, active={self._active}, members={self.member_count})"


async def create_sitting_manager(
    room_id: str,
    event_log: EventLog,
    owner_id: str,
    config: Optional[SittingConfig] = None,
    on_sitting_ended: Optional[Callable[[str, SittingEndedEvent], None]] = None,
) -> SittingManager:
    """Factory function to create and start a sitting manager."""
    manager = SittingManager(
        room_id=room_id,
        event_log=event_log,
        owner_id=owner_id,
        config=config,
        on_sitting_ended=on_sitting_ended,
    )
    await manager.start()
    return manager