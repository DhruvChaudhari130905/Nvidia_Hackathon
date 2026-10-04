"""Shared FastAPI dependencies: current user from the Supabase JWT, room lookup, permission checks."""

import logging
from typing import Optional
from fastapi import Depends, HTTPException, status, Path
from mux.auth.supabase import get_current_user, get_current_user_optional, User
from mux.auth.permissions import has_permission
from mux.rooms.actor import RoomActor, ROOM_ID_PATTERN
from mux.rooms.registry import get_registry

logger = logging.getLogger(__name__)


async def get_room_actor_dep(
    room_id: str = Path(...),
    current_user: User = Depends(get_current_user),
) -> RoomActor:
    """
    Get the RoomActor for an existing room, rehydrating it from the event log if needed.

    Rooms are only created by POST /api/rooms; an unknown or closed room is a 404.
    (Previously any request for an unknown id created the room and made the caller owner.)
    """
    if not ROOM_ID_PATTERN.match(room_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    actor = await get_registry().get_room_or_rehydrate(room_id)
    if actor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return actor


class RoomActorPermissionChecker:
    """Permission checker that works with RoomActor."""

    def __init__(self, actor: RoomActor):
        self.actor = actor

    async def get_user_role(self, user_id: str) -> Optional[str]:
        """
        Get the user's role in this room: owner, a granted member role,
        viewer for public rooms, otherwise None. Presence does not grant access.
        """
        return self.actor.role_of(user_id)


def get_user_permission_checker(required_permission: str):
    """
    Dependency factory to create a permission checker for a required permission.

    Args:
        required_permission: The permission to check (e.g., "owner", "editor", "viewer").

    Returns:
        A dependency function that takes the current user and room actor, checks permissions,
        and returns the current user on success.
    """
    async def _permission_checker(
        current_user: User = Depends(get_current_user),
        actor: RoomActor = Depends(get_room_actor_dep),
    ) -> User:
        """
        Check if the current user has the required permission on the given room.

        Raises:
            HTTPException: If the user does not have the required permission.
        """
        checker = RoomActorPermissionChecker(actor)
        user_role = await checker.get_user_role(current_user.id)

        if user_role is None:
            logger.warning(
                f"User {current_user.id} has no role in room {actor.room_id}. "
                f"Cannot check permission '{required_permission}'."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions: no role in room"
            )

        if not has_permission(user_role, required_permission):
            logger.warning(
                f"User {current_user.id} (role: {user_role}) lacks required permission "
                f"'{required_permission}' on room {actor.room_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: requires {required_permission}"
            )

        return current_user

    return _permission_checker


# Common permission dependencies
require_owner = get_user_permission_checker("owner")
require_editor = get_user_permission_checker("editor")
require_viewer = get_user_permission_checker("viewer")
