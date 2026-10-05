"""A room's budget of tokens and sandbox runs. The room is paused while a cap is reached, until the owner
raises it (PRD §5.1, guardrails). Usage lives in `budgets`, caps in `rooms`; the paused state follows from them."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mux.db import tables
from mux.events.log import scoped
from mux.events.models import BudgetLimit, BudgetUpdated

DEFAULT_TOKENS_CAP = 2_000_000
DEFAULT_RUNS_CAP = 100


@dataclass(frozen=True)
class Budget:
    """Usage and caps of one room."""

    tokens_used: int = 0
    runs_used: int = 0
    tokens_cap: int = DEFAULT_TOKENS_CAP
    runs_cap: int = DEFAULT_RUNS_CAP

    @property
    def over(self) -> BudgetLimit | None:
        """The cap that is reached, or None. The room is paused while one is."""
        if self.tokens_used >= self.tokens_cap:
            return "tokens"
        if self.runs_used >= self.runs_cap:
            return "runs"
        return None

    def payload(self) -> BudgetUpdated:
        return BudgetUpdated(
            tokens_used=self.tokens_used, runs_used=self.runs_used, tokens_cap=self.tokens_cap, runs_cap=self.runs_cap,
        )


async def load(room_id: UUID, *, session: AsyncSession | None = None) -> Budget:
    """The stored budget. A room with no usage yet has no row; unset caps use the defaults."""
    async with scoped(session) as s:
        caps = (await s.execute(
            select(tables.Room.budget_tokens_cap, tables.Room.budget_runs_cap).where(tables.Room.id == room_id)
        )).one()
        used = (await s.execute(
            select(tables.Budget.tokens_used, tables.Budget.runs_used).where(tables.Budget.room_id == room_id)
        )).one_or_none()
    return Budget(
        tokens_used=used.tokens_used if used else 0,
        runs_used=used.runs_used if used else 0,
        tokens_cap=caps.budget_tokens_cap or DEFAULT_TOKENS_CAP,
        runs_cap=caps.budget_runs_cap or DEFAULT_RUNS_CAP,
    )


async def add_usage(room_id: UUID, tokens: int, runs: int, *, session: AsyncSession | None = None) -> None:
    """Add to the stored usage. The row is created on first use."""
    stmt = insert(tables.Budget).values(room_id=room_id, tokens_used=tokens, runs_used=runs)
    async with scoped(session) as s:
        await s.execute(stmt.on_conflict_do_update(
            index_elements=[tables.Budget.room_id],
            set_ = {
                "tokens_used": tables.Budget.tokens_used + stmt.excluded.tokens_used,
                "runs_used": tables.Budget.runs_used + stmt.excluded.runs_used,
                "updated_at": func.now(),  # onupdate= only fires for ORM updates
            }
        ))


async def set_caps(room_id: UUID, tokens_cap: int, runs_cap: int, *, session: AsyncSession | None = None) -> None:
    """Store new caps on the room."""
    async with scoped(session) as s:
        await s.execute(
            update(tables.Room).where(tables.Room.id == room_id).values(budget_tokens_cap=tokens_cap, budget_runs_cap=runs_cap)
        )
