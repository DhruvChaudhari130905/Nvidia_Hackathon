"""Token and sandbox-run accounting per room. Pauses the room at the cap until the owner raises it."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, TypedDict
from uuid import uuid4
from datetime import datetime, timezone

from mux.events.models import BudgetExceededEvent, EventType
from mux.events.log import EventLog

logger = logging.getLogger(__name__)


class BudgetStatus(TypedDict):
    """Typed budget status for external consumers."""
    tokens_used: int
    token_cap: int
    token_pct: float
    sandbox_runs_used: int
    sandbox_run_cap: int
    sandbox_run_pct: float
    paused: bool
    paused_reason: Optional[str]
    paused_at: Optional[float]


@dataclass(frozen=True, slots=True)
class BudgetConfig:
    """Configuration for budget limits."""
    token_cap: int = 1_000_000          # Max tokens per sitting
    sandbox_run_cap: int = 100          # Max sandbox runs per sitting
    warning_threshold: float = 0.8      # Warn at 80% of cap


@dataclass(frozen=True, slots=True)
class BudgetState:
    """Current budget consumption (immutable)."""
    tokens_used: int = 0
    sandbox_runs_used: int = 0
    token_cap: int = 1_000_000
    sandbox_run_cap: int = 100
    paused: bool = False
    paused_at: Optional[float] = None
    paused_reason: Optional[str] = None

    @property
    def token_pct(self) -> float:
        return self.tokens_used / self.token_cap if self.token_cap > 0 else 0.0

    @property
    def sandbox_run_pct(self) -> float:
        return self.sandbox_runs_used / self.sandbox_run_cap if self.sandbox_run_cap > 0 else 0.0

    @property
    def is_over_token_cap(self) -> bool:
        return self.tokens_used >= self.token_cap

    @property
    def is_over_sandbox_cap(self) -> bool:
        return self.sandbox_runs_used >= self.sandbox_run_cap

    def is_at_warning(self, threshold: float = 0.8) -> bool:
        return self.token_pct >= threshold or self.sandbox_run_pct >= threshold

    def with_tokens(self, delta: int) -> "BudgetState":
        return BudgetState(
            tokens_used=self.tokens_used + delta,
            sandbox_runs_used=self.sandbox_runs_used,
            token_cap=self.token_cap,
            sandbox_run_cap=self.sandbox_run_cap,
            paused=self.paused,
            paused_at=self.paused_at,
            paused_reason=self.paused_reason,
        )

    def with_sandbox_run(self) -> "BudgetState":
        return BudgetState(
            tokens_used=self.tokens_used,
            sandbox_runs_used=self.sandbox_runs_used + 1,
            token_cap=self.token_cap,
            sandbox_run_cap=self.sandbox_run_cap,
            paused=self.paused,
            paused_at=self.paused_at,
            paused_reason=self.paused_reason,
        )

    def with_pause(self, reason: str) -> "BudgetState":
        return BudgetState(
            tokens_used=self.tokens_used,
            sandbox_runs_used=self.sandbox_runs_used,
            token_cap=self.token_cap,
            sandbox_run_cap=self.sandbox_run_cap,
            paused=True,
            paused_at=time.monotonic(),
            paused_reason=reason,
        )

    def with_resume(self) -> "BudgetState":
        return BudgetState(
            tokens_used=self.tokens_used,
            sandbox_runs_used=self.sandbox_runs_used,
            token_cap=self.token_cap,
            sandbox_run_cap=self.sandbox_run_cap,
            paused=False,
            paused_at=None,
            paused_reason=None,
        )

    def with_new_caps(self, token_cap: int, sandbox_run_cap: int) -> "BudgetState":
        return BudgetState(
            tokens_used=self.tokens_used,
            sandbox_runs_used=self.sandbox_runs_used,
            token_cap=token_cap,
            sandbox_run_cap=sandbox_run_cap,
            paused=self.paused,
            paused_at=self.paused_at,
            paused_reason=self.paused_reason,
        )


class BudgetManager:
    """
    Manages token and sandbox-run budget for a room.

    When either cap is exceeded, the room is paused.
    Owner can raise caps to resume.
    """

    def __init__(
        self,
        room_id: str,
        event_log: EventLog,
        owner_id: str,
        config: Optional[BudgetConfig] = None,
        *,
        on_pause: Optional[Callable[[str, str], None]] = None,
        on_resume: Optional[Callable[[str], None]] = None,
        on_warning: Optional[Callable[[str, float, float], None]] = None,
    ) -> None:
        self.room_id = room_id
        self.event_log = event_log
        self.owner_id = owner_id
        self.config = config or BudgetConfig()
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_warning = on_warning

        self._state = BudgetState(
            token_cap=self.config.token_cap,
            sandbox_run_cap=self.config.sandbox_run_cap,
        )
        self._lock = asyncio.Lock()
        self._warned = False

    @property
    def state(self) -> BudgetState:
        return self._state

    @property
    def is_paused(self) -> bool:
        return self._state.paused

    async def record_tokens(self, delta: int, user_id: str) -> bool:
        """
        Record token usage.
        Returns True if allowed, False if room is paused and would exceed cap.
        """
        if delta <= 0:
            return True

        fire_callback = None
        async with self._lock:
            if self._state.paused:
                # Allow if user is owner raising cap, otherwise deny
                if user_id != self.owner_id:
                    return False

            new_state = self._state.with_tokens(delta)
            self._state = new_state

            # Check for cap exceeded
            if new_state.is_over_token_cap and not new_state.paused:
                fire_callback = await self._pause_room("token_cap_exceeded")

            # Check for warning threshold
            elif new_state.is_at_warning(self.config.warning_threshold) and not self._warned:
                self._warned = True
                if self._on_warning:
                    callback = self._on_warning
                    def _fire():
                        try:
                            callback(self.room_id, new_state.token_pct, new_state.sandbox_run_pct)
                        except Exception:
                            logger.exception("on_warning callback failed")
                    fire_callback = _fire

            return True
        if fire_callback:
            fire_callback()
        return True

    async def record_sandbox_run(self, user_id: str) -> bool:
        """
        Record a sandbox run.
        Returns True if allowed, False if room is paused and would exceed cap.
        """
        fire_callback = None
        async with self._lock:
            if self._state.paused:
                if user_id != self.owner_id:
                    return False

            new_state = self._state.with_sandbox_run()
            self._state = new_state

            if new_state.is_over_sandbox_cap and not new_state.paused:
                fire_callback = await self._pause_room("sandbox_run_cap_exceeded")

            elif new_state.is_at_warning(self.config.warning_threshold) and not self._warned:
                self._warned = True
                if self._on_warning:
                    callback = self._on_warning
                    def _fire():
                        try:
                            callback(self.room_id, new_state.token_pct, new_state.sandbox_run_pct)
                        except Exception:
                            logger.exception("on_warning callback failed")
                    fire_callback = _fire

            return True
        if fire_callback:
            fire_callback()
        return True

    async def check_allowance(self, estimated_tokens: int = 0, estimated_runs: int = 0) -> bool:
        """Check if an operation would be allowed without recording it."""
        async with self._lock:
            if self._state.paused:
                return False
            if estimated_tokens and (self._state.tokens_used + estimated_tokens) > self._state.token_cap:
                return False
            if estimated_runs and (self._state.sandbox_runs_used + estimated_runs) > self._state.sandbox_run_cap:
                return False
            return True

    async def raise_caps(self, user_id: str, token_cap: Optional[int] = None, sandbox_run_cap: Optional[int] = None) -> bool:
        """
        Raise budget caps (owner only).
        If room was paused and new caps cover current usage, auto-resume.
        """
        if user_id != self.owner_id:
            return False

        fire_callback = None
        async with self._lock:
            new_token_cap = token_cap if token_cap is not None else self._state.token_cap
            new_sandbox_cap = sandbox_run_cap if sandbox_run_cap is not None else self._state.sandbox_run_cap

            if new_token_cap <= self._state.token_cap and new_sandbox_cap <= self._state.sandbox_run_cap:
                return False  # No increase

            was_paused = self._state.paused
            self._state = self._state.with_new_caps(new_token_cap, new_sandbox_cap)

            # Auto-resume if caps now cover usage
            if was_paused and not self._state.is_over_token_cap and not self._state.is_over_sandbox_cap:
                fire_callback = await self._resume_room()

            return True
        if fire_callback:
            fire_callback()
        return True

    async def force_resume(self, user_id: str) -> bool:
        """Force resume without raising caps (owner only)."""
        if user_id != self.owner_id:
            return False

        fire_callback = None
        async with self._lock:
            if not self._state.paused:
                return True
            fire_callback = await self._resume_room()
            return True
        if fire_callback:
            fire_callback()
        return True

    # --- Public methods expected by registry.py ---

    async def pause(self, reason: str) -> Callable[[], None] | None:
        """Public pause method (called during rehydration)."""
        return await self._pause_room(reason)

    async def resume(self) -> Callable[[], None] | None:
        """Public resume method (called during rehydration)."""
        return await self._resume_room()

    async def _pause_room(self, reason: str) -> Callable[[], None] | None:
        """Pause the room and emit event. Returns callback to fire after lock released."""
        self._state = self._state.with_pause(reason)

        event = BudgetExceededEvent(
            id=uuid4(),
            type=EventType.BUDGET_EXCEEDED,
            room_id=self.room_id,
            user_id=self.owner_id,
            timestamp=datetime.now(timezone.utc),
            sequence=0,  # EventLog will assign sequence
            prev_event_id=None,
            reason=reason,
            tokens_used=self._state.tokens_used,
            token_cap=self._state.token_cap,
            sandbox_runs_used=self._state.sandbox_runs_used,
            sandbox_run_cap=self._state.sandbox_run_cap,
        )
        await self.event_log.append(event)

        if self._on_pause:

            callback = self._on_pause
            def _fire():
                try:
                    callback(self.room_id, reason)
                except Exception:
                    logger.exception("on_pause callback failed")
            return _fire
        return None

    async def _resume_room(self) -> Callable[[], None] | None:
        """Resume the room and emit event. Returns callback to fire after lock released."""
        self._state = self._state.with_resume()
        self._warned = False

        event = BudgetExceededEvent(
            id=uuid4(),
            type=EventType.BUDGET_RESUMED,
            room_id=self.room_id,
            user_id=self.owner_id,
            timestamp=datetime.now(timezone.utc),
            sequence=0,  # EventLog will assign sequence
            prev_event_id=None,
            reason="resumed",
            tokens_used=self._state.tokens_used,
            token_cap=self._state.token_cap,
            sandbox_runs_used=self._state.sandbox_runs_used,
            sandbox_run_cap=self._state.sandbox_run_cap,
        )
        await self.event_log.append(event)

        if self._on_resume:

            callback = self._on_resume
            def _fire():
                try:
                    callback(self.room_id)
                except Exception:
                    logger.exception("on_resume callback failed")
            return _fire
        return None

    async def get_status(self) -> BudgetStatus:
        """Get current budget status (typed)."""
        async with self._lock:
            return BudgetStatus(
                tokens_used=self._state.tokens_used,
                token_cap=self._state.token_cap,
                token_pct=self._state.token_pct,
                sandbox_runs_used=self._state.sandbox_runs_used,
                sandbox_run_cap=self._state.sandbox_run_cap,
                sandbox_run_pct=self._state.sandbox_run_pct,
                paused=self._state.paused,
                paused_reason=self._state.paused_reason,
                paused_at=self._state.paused_at,
            )

    def __len__(self) -> int:
        """Always 1 (single budget per room) — for debugging."""
        return 1

    def __repr__(self) -> str:
        return f"BudgetManager(room_id={self.room_id!r}, tokens={self._state.tokens_used}/{self._state.token_cap}, runs={self._state.sandbox_runs_used}/{self._state.sandbox_run_cap}, paused={self._state.paused})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BudgetManager):
            return NotImplemented
        return self.room_id == other.room_id


async def create_budget_manager(
    room_id: str,
    event_log: EventLog,
    owner_id: str,
    config: Optional[BudgetConfig] = None,
    on_pause: Optional[Callable[[str, str], None]] = None,
    on_resume: Optional[Callable[[str], None]] = None,
    on_warning: Optional[Callable[[str, float, float], None]] = None,
) -> BudgetManager:
    """Factory function to create a budget manager."""
    return BudgetManager(
        room_id=room_id,
        event_log=event_log,
        owner_id=owner_id,
        config=config,
        on_pause=on_pause,
        on_resume=on_resume,
        on_warning=on_warning,
    )