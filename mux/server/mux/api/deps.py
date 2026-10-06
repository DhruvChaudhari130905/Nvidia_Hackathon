"""FastAPI dependencies: the user from the Supabase JWT, the room's actor, and the caller's permission in it."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from mux.auth.permissions import has_permission
from mux.auth.supabase import http_bearer, verify_supabase_token
from mux.events.models import Permission
from mux.rooms.actor import RoomActor
from mux.rooms.registry import get_registry


@dataclass(frozen=True)
class CurrentUser:
    """The signed-in user. `id` is the Supabase user id (the JWT's `sub`)."""

    id: UUID
    name: str | None


@dataclass(frozen=True)
class RoomAccess:
    """A room the caller may use, with their permission in it."""

    actor: RoomActor
    user: CurrentUser
    permission: Permission


def user_from_token(token: str | None) -> CurrentUser | None:
    """The user a Supabase JWT belongs to, or None if the token is missing, invalid, or its `sub` is not a UUID."""
    claims = verify_supabase_token(token) if token else None
    if claims is None:
        return None
    try:
        user_id = UUID(str(claims.get("sub")))
    except ValueError:
        return None
    return CurrentUser(user_id, _name(claims))


def _name(claims: dict[str, Any]) -> str | None:
    """Supabase keeps the display name in user_metadata (full_name or name); fall back to the email."""
    meta = claims.get("user_metadata")
    if isinstance(meta, dict) and (meta.get("full_name") or meta.get("name")):
        return meta.get("full_name") or meta.get("name")
    return claims.get("email")


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)],
) -> CurrentUser:
    """The caller, from the Authorization: Bearer header. 401 without a valid token."""
    user = user_from_token(credentials.credentials if credentials else None)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in", headers={"WWW-Authenticate": "Bearer"})
    return user


async def room_actor(room_id: UUID) -> RoomActor:
    """The room's actor, opened from the database if needed. 404 if there is no such room."""
    actor = await get_registry().get(room_id)
    if actor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "room not found")
    return actor


def require(level: Permission) -> Callable[..., Awaitable[RoomAccess]]:
    """A dependency that lets the caller in only with at least `level` in the room.
    A room they cannot open at all is a 404, so its existence does not leak."""

    async def check(
        user: Annotated[CurrentUser, Depends(current_user)], actor: Annotated[RoomActor, Depends(room_actor)]
    ) -> RoomAccess:
        permission = actor.role_of(user.id)
        if permission is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "room not found")
        if not has_permission(permission, level):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"needs {level} permission")
        return RoomAccess(actor, user, permission)

    return check


User = Annotated[CurrentUser, Depends(current_user)]
Actor = Annotated[RoomActor, Depends(room_actor)]
Viewer = Annotated[RoomAccess, Depends(require("viewer"))]
Editor = Annotated[RoomAccess, Depends(require("editor"))]
Owner = Annotated[RoomAccess, Depends(require("owner"))]
