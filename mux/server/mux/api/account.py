"""The signed-in user's plan (mux/plans.py): read it, or switch to another one."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mux.api.deps import User, get_current_user
from mux.events.file_log import stored_room_ids
from mux.plans import Plan, PlanName, apply_plan_caps, get_plan, set_plan
from mux.rooms.registry import get_registry

router = APIRouter()


class PlanRequest(BaseModel):
    plan: PlanName


async def owned_room_actors(user_id: str) -> list[Any]:
    """Every open room the user owns, running or saved on disk."""
    registry = get_registry()
    owned = []
    for room_id in sorted(set(await registry.list_rooms()) | set(stored_room_ids())):
        actor = await registry.get_room_or_rehydrate(room_id)
        if actor and actor.owner_id == user_id:
            owned.append(actor)
    return owned


def plan_view(plan: Plan, rooms_owned: int) -> dict[str, Any]:
    return {
        "plan": plan.name,
        "label": plan.label,
        "room_limit": plan.room_limit,
        "token_cap": plan.token_cap,
        "run_cap": plan.run_cap,
        "rooms_owned": rooms_owned,
    }


@router.get("/plan")
async def read_plan(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return plan_view(get_plan(current_user.id), len(await owned_room_actors(current_user.id)))


@router.put("/plan")
async def change_plan(request: PlanRequest, current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Switch plans now (no payment step yet). Upgrading also raises the budget of every room the user owns."""
    plan = set_plan(current_user.id, request.plan)
    owned = await owned_room_actors(current_user.id)
    for actor in owned:
        await apply_plan_caps(actor)
    return plan_view(plan, len(owned))
