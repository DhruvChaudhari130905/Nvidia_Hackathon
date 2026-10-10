"""Plans: how many rooms a user may own and how big each room's budget is.

There are no payments yet: choosing a plan on the Pricing page applies it straight away. Plans are kept in
<cwd>/.mux/plans.json (next to the room event logs), and each room's caps are raised to its owner's plan
when the room is created or rebuilt after a restart, so an upgrade survives restarts.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from mux.rooms.actor import RoomActor

logger = logging.getLogger(__name__)

PlanName = Literal["free", "pro", "enterprise"]


@dataclass(frozen=True, slots=True)
class Plan:
    name: PlanName
    label: str
    room_limit: Optional[int]  # rooms the user may own; None: no limit
    token_cap: int  # per room
    run_cap: int  # sandbox builds per room


# Free matches the budget every room had before plans existed, so nothing shrinks for anyone
PLANS: dict[str, Plan] = {
    "free": Plan("free", "Free Developer", room_limit=3, token_cap=1_000_000, run_cap=100),
    "pro": Plan("pro", "Team Pro", room_limit=None, token_cap=5_000_000, run_cap=500),
    "enterprise": Plan("enterprise", "Enterprise", room_limit=None, token_cap=20_000_000, run_cap=2_000),
}

_lock = threading.Lock()


def plans_path() -> Path:
    return Path.cwd() / ".mux" / "plans.json"


def _read() -> dict[str, str]:
    path = plans_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError) as e:
        logger.error(f"{path}: unreadable plans file, treating everyone as Free: {e}")
        return {}


def get_plan(user_id: str) -> Plan:
    with _lock:
        return PLANS.get(_read().get(user_id, "free"), PLANS["free"])


def set_plan(user_id: str, name: str) -> Plan:
    if name not in PLANS:
        raise ValueError(f"unknown plan {name!r}")
    with _lock:
        data = _read()
        data[user_id] = name
        path = plans_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)  # never leave a half-written file behind
    logger.info(f"User {user_id} is now on the {name} plan")
    return PLANS[name]


async def apply_plan_caps(actor: "RoomActor") -> None:
    """Raise the room's budget to its owner's plan. Caps only ever go up here, so a downgrade leaves
    existing rooms alone and only new rooms get the smaller budget."""
    plan = get_plan(actor.owner_id)
    await actor.raise_budget_caps(actor.owner_id, token_cap=plan.token_cap, sandbox_run_cap=plan.run_cap)
