"""Which skills (mux/skills) a room's coder may use: everyone in the room sees them, the owner chooses."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import mux.skills.library as skills_library
from mux.api.deps import User, get_room_actor_dep, require_owner, require_viewer
from mux.rooms.actor import RoomActor

router = APIRouter()

MAX_ENABLED_SKILLS = 30


class SkillsRequest(BaseModel):
    enabled: list[str] = Field(default_factory=list, max_length=200)


def skills_view(actor: RoomActor) -> list[dict[str, Any]]:
    available = skills_library.library().skills()
    rows = [{
        "name": s.name, "description": s.description, "source": s.source, "compatible": s.compatible,
        "issues": s.issues, "enabled": s.name in actor.skills_enabled, "files": len(s.files), "missing": False,
    } for s in available.values()]
    rows += [{"name": name, "description": "", "source": "", "compatible": True, "issues": [], "enabled": True,
              "files": 0, "missing": True} for name in actor.skills_enabled if name not in available]
    return sorted(rows, key=lambda row: row["name"])


@router.get("/{room_id}/skills")
async def get_skills(room_id: str, current_user: User = Depends(require_viewer),
                     actor: RoomActor = Depends(get_room_actor_dep)) -> list[dict[str, Any]]:
    return skills_view(actor)


@router.put("/{room_id}/skills")
async def set_skills(room_id: str, request: SkillsRequest, current_user: User = Depends(require_owner),
                     actor: RoomActor = Depends(get_room_actor_dep)) -> list[dict[str, Any]]:
    wanted = set(request.enabled)
    known = set(skills_library.library().skills()) | actor.skills_enabled  # missing ones may stay switched on
    unknown = sorted(wanted - known)
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No skill named {', '.join(unknown)}")
    if len(wanted) > MAX_ENABLED_SKILLS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"A room can have at most {MAX_ENABLED_SKILLS} skills on")
    await actor.set_skills(sorted(wanted), current_user.id)
    return skills_view(actor)


@router.post("/{room_id}/skills/reload")
async def reload_skills(room_id: str, current_user: User = Depends(require_owner),
                        actor: RoomActor = Depends(get_room_actor_dep)) -> list[dict[str, Any]]:
    skills_library.library().reload()
    return skills_view(actor)
