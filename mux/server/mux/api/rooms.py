"""Create, list, and fetch rooms. Sharing settings, invites, and memberships."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from mux.api.deps import get_room_actor_dep, get_current_user, require_editor, require_owner, require_viewer, User
from mux.rooms.registry import get_registry
from mux.rooms.actor import RoomActor
from mux.events.models import EventType
from mux.api.files import (
    FileLockResponse, FileUnlockResponse, FileUpdateResponse, FileDeleteResponse
)
from mux.api.commands import (
    CommandEditPlanResponse, CommandApprovePlanResponse, CommandVoteResponse,
    CommandOverrideResponse, CommandAnswerQuestionResponse, CommandRewindResponse,
    CommandRaiseBudgetResponse
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class RoomCreateRequest(BaseModel):
    """Request to create a new room."""
    name: str = Field(..., min_length=1, max_length=200, description="Room name")
    description: Optional[str] = Field(None, max_length=2000, description="Room description")
    initial_plan: Optional[list[dict]] = Field(None, description="Initial plan items")
    # Frontend-compatible fields
    domain_role: Optional[str] = Field(None, description="Domain role (frontend compatibility)")


class RoomCreateResponse(BaseModel):
    """Response after creating a room."""
    room_id: str
    name: str
    description: Optional[str]
    owner_id: str
    created: bool  # True if newly created, False if rehydrated


class RoomJoinRequest(BaseModel):
    """Request to join a room."""
    user_name: Optional[str] = Field(None, max_length=100, description="Display name")
    avatar_url: Optional[str] = Field(None, description="Avatar URL")


class RoomJoinResponse(BaseModel):
    """Response after joining a room."""
    user_id: str
    user_name: Optional[str]
    avatar_url: Optional[str]
    status: str
    joined_at: str


class RoomStatusResponse(BaseModel):
    """Current room status snapshot."""
    room_id: str
    owner_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    active_members: int
    plan_items: int
    budget: dict
    sitting_active: bool
    sitting_idle_seconds: Optional[float]
    locks_held: int
    files_count: int
    running: bool


class RoomListResponse(BaseModel):
    """List of rooms."""
    rooms: list[dict]


class RoomLeaveResponse(BaseModel):
    """Response after leaving a room."""
    user_id: str
    left: bool


class RoomCloseResponse(BaseModel):
    """Response after closing a room."""
    room_id: str
    closed: bool
    reason: Optional[str]


# Frontend-compatible models
class RoomSharingUpdateRequest(BaseModel):
    """Request to update room sharing settings."""
    public: bool = Field(..., description="Whether room is publicly accessible")
    allow_anonymous: bool = Field(False, description="Allow anonymous access")


class MemberAddRequest(BaseModel):
    """Request to grant a user membership in a room (owner only)."""
    user_id: str = Field(..., min_length=1, max_length=200, description="User to add")
    role: Literal["editor", "viewer"] = Field("editor", description="Role to grant")


class MemberResponse(BaseModel):
    """Response after granting membership."""
    room_id: str
    user_id: str
    role: str
    sequence: int


class RoomSharingResponse(BaseModel):
    """Response after updating sharing settings."""
    room_id: str
    public: bool
    allow_anonymous: bool
    updated: bool


class MessageCreateRequest(BaseModel):
    """Request to send a chat message."""
    content: str = Field(..., min_length=1, max_length=10000, description="Message content")
    reply_to: Optional[str] = Field(None, description="Message ID being replied to")


class MessageResponse(BaseModel):
    """Response after sending a message."""
    message_id: str
    sequence: int
    event_type: str = "message_posted"


class PlanUpdateRequest(BaseModel):
    """Request to update the plan (frontend-compatible)."""
    items: List[dict] = Field(..., description="Plan items")


class PlanApproveRequest(BaseModel):
    """Request to approve plan items (frontend-compatible)."""
    plan_item_ids: List[str] = Field(..., min_length=1, description="IDs of plan items to approve")


class ConflictVoteRequest(BaseModel):
    """Request to vote on a conflict (frontend-compatible)."""
    option_id: str = Field(..., description="ID of option being voted for")
    vote_value: bool = Field(..., description="Vote value (true/false)")
    plan_item_id: Optional[str] = Field(None, description="Specific plan item being voted on")


class ConflictOverrideRequest(BaseModel):
    """Request to override a conflict (frontend-compatible)."""
    new_plan: List[dict] = Field(..., description="New plan to replace current one")
    reason: Optional[str] = Field(None, description="Reason for override")


class QuestionAnswerRequest(BaseModel):
    """Request to answer a question (frontend-compatible)."""
    question_id: str = Field(..., description="ID of the question being answered")
    answer: str = Field(..., min_length=1, max_length=10000, description="The answer text")


class FileLockRequest(BaseModel):
    """Request to lock a file (frontend-compatible with path in body)."""
    path: str = Field(..., min_length=1, max_length=500, description="File path")


class FileUnlockRequest(BaseModel):
    """Request to unlock a file (frontend-compatible with path in body)."""
    path: str = Field(..., min_length=1, max_length=500, description="File path")


class FileUpdateRequestFrontend(BaseModel):
    """Request to update a file (frontend-compatible with path in body)."""
    path: str = Field(..., min_length=1, max_length=500, description="File path")
    content: str = Field(..., description="New file content")
    base_version: Optional[int] = Field(None, description="Expected base version for optimistic locking")


class RewindRequest(BaseModel):
    """Request to rewind (frontend-compatible with checkpoint_id)."""
    checkpoint_id: str = Field(..., description="Checkpoint ID to rewind to")


class BudgetUpdateRequest(BaseModel):
    """Request to update budget (frontend-compatible)."""
    tokens_cap: Optional[int] = Field(None, ge=1, description="New token cap")
    runs_cap: Optional[int] = Field(None, ge=1, description="New sandbox run cap")


# =============================================================================
# Helper: Get RoomActor for a room (creates/rehydrates if needed)
# =============================================================================

# Shared dependency: looks up (or rehydrates) an existing room; never creates one.
get_room_actor = get_room_actor_dep


# =============================================================================
# Endpoints
# =============================================================================

@router.post("", response_model=RoomCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    request: RoomCreateRequest,
    current_user: User = Depends(get_current_user),
) -> RoomCreateResponse:
    """
    Create a new room with the current user as owner.
    """
    registry = get_registry()

    # Generate a room ID using UUID (in production, this would come from the database)
    room_id = f"room_{uuid.uuid4().hex[:12]}"

    # Create the room actor (records ROOM_CREATED with owner and metadata)
    actor = await registry.create_room(
        room_id, current_user.id, name=request.name, description=request.description
    )

    if request.initial_plan:
        try:
            await actor.draft_plan(request.initial_plan, current_user.id)
        except ValueError:
            # Don't leave a half-created room behind
            await actor.close_room(current_user.id, "invalid initial plan")
            await registry.stop_room(room_id, reason="invalid initial plan")
            raise

    return RoomCreateResponse(
        room_id=room_id,
        name=request.name,
        description=request.description,
        owner_id=current_user.id,
        created=True,
    )


@router.get("", response_model=RoomListResponse)
async def list_rooms(
    current_user: User = Depends(get_current_user),
) -> RoomListResponse:
    """
    List active rooms (rooms with running actors) the current user can access.
    Note: In production, this would query a database for all rooms the user has access to.
    """
    registry = get_registry()
    room_ids = await registry.list_rooms()

    rooms = []
    for room_id in room_ids:
        actor = await registry.get_room(room_id)
        if actor and actor.role_of(current_user.id) is not None:
            rooms.append(await get_room_status(actor))

    return RoomListResponse(rooms=rooms)


@router.get("/{room_id}", response_model=RoomStatusResponse)
async def get_room_endpoint(
    room_id: str,
    current_user: User = Depends(require_viewer),
    actor: RoomActor = Depends(get_room_actor),
) -> RoomStatusResponse:
    """
    Get detailed status of a room.
    Requires viewer permission.
    """
    return await get_room_status(actor)


@router.post("/{room_id}/join", response_model=RoomJoinResponse)
async def join_room(
    room_id: str,
    request: RoomJoinRequest,
    current_user: User = Depends(get_current_user),
    actor: RoomActor = Depends(get_room_actor),
) -> RoomJoinResponse:
    """
    Join a room as a participant.

    Owners and members can always join. In a public room, joining grants editor
    membership. Private rooms require the owner to add you first (POST /members).
    """
    role = actor.role_of(current_user.id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This room is private; ask the owner to add you"
        )
    if actor.public and current_user.id != actor.owner_id and current_user.id not in actor.members:
        await actor.add_member(current_user.id, "editor", granted_by=current_user.id, user_name=request.user_name)

    presence = await actor.user_join(
        user_id=current_user.id,
        user_name=request.user_name,
        avatar_url=request.avatar_url,
    )

    return RoomJoinResponse(
        user_id=current_user.id,
        user_name=presence.user_name,
        avatar_url=presence.avatar_url,
        status=presence.status,
        # presence.joined_at is a monotonic clock value, not wall time
        joined_at=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/{room_id}/leave", response_model=RoomLeaveResponse)
async def leave_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    actor: RoomActor = Depends(get_room_actor),
) -> RoomLeaveResponse:
    """
    Leave a room.
    """
    await actor.user_leave(current_user.id)

    return RoomLeaveResponse(
        user_id=current_user.id,
        left=True,
    )


@router.post("/{room_id}/close", response_model=RoomCloseResponse)
async def close_room(
    room_id: str,
    reason: Optional[str] = Query(None, description="Reason for closing"),
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> RoomCloseResponse:
    """
    Close a room (owner only).
    Stops the room actor and cleans up.
    """
    registry = get_registry()
    # Record the close so the room is not rehydrated (and re-claimed) later
    await actor.close_room(current_user.id, reason)
    await registry.stop_room(room_id, reason=reason or "closed_by_owner")

    return RoomCloseResponse(
        room_id=room_id,
        closed=True,
        reason=reason,
    )


# =============================================================================
# Room Status Helpers
# =============================================================================

async def get_room_status(actor: RoomActor) -> dict:
    """Get a comprehensive status snapshot of the room."""
    # Get plan info
    plan_items = await actor.plan.get_items()

    # Get budget status
    budget_status = await actor.budget.get_status()

    # Get sitting status
    sitting_status = await actor.sitting.get_status()

    # Get presence info
    members = await actor.presence.get_all()

    # Get locks info
    locks = await actor.locks.get_all_locks()

    # Get files count
    files_count = len(actor.manifest.entries)

    # Get room metadata
    room_meta = actor.manifest.get_room_metadata()

    return {
        "room_id": actor.room_id,
        "owner_id": actor.owner_id,
        "name": room_meta.get("name"),
        "description": room_meta.get("description"),
        "active_members": len(members),
        "plan_items": len(plan_items),
        "budget": budget_status,
        "sitting_active": sitting_status["active"],
        "sitting_idle_seconds": sitting_status.get("idle_seconds"),
        "locks_held": len(locks),
        "files_count": files_count,
        "running": actor.is_running(),
    }


# =============================================================================
# Frontend-Compatible Endpoints
# =============================================================================

@router.patch("/{room_id}/sharing", response_model=RoomSharingResponse)
async def update_room_sharing(
    room_id: str,
    request: RoomSharingUpdateRequest,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> RoomSharingResponse:
    """
    Update room sharing settings (owner only).
    Frontend-compatible endpoint. Public rooms are viewable by any signed-in user,
    and joining one grants editor membership.
    """
    await actor.set_sharing(request.public, request.allow_anonymous, current_user.id)
    return RoomSharingResponse(
        room_id=room_id,
        public=request.public,
        allow_anonymous=request.allow_anonymous,
        updated=True,
    )


@router.post("/{room_id}/members", response_model=MemberResponse)
async def add_member(
    room_id: str,
    request: MemberAddRequest,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> MemberResponse:
    """
    Grant a user editor or viewer membership (owner only).
    """
    await actor.add_member(request.user_id, request.role, granted_by=current_user.id)
    return MemberResponse(
        room_id=room_id,
        user_id=request.user_id,
        role=request.role,
        sequence=actor._state.sequence,
    )


@router.post("/{room_id}/messages", response_model=MessageResponse)
async def send_message(
    room_id: str,
    request: MessageCreateRequest,
    current_user: User = Depends(require_editor),
    actor: RoomActor = Depends(get_room_actor),
) -> MessageResponse:
    """
    Send a chat message to the room (editor+).
    Frontend-compatible endpoint.
    """
    message_id = str(uuid.uuid4())
    await actor.add_message(
        label="chat",
        content=request.content,
        message_id=message_id,
        user_id=current_user.id,
    )
    return MessageResponse(
        message_id=message_id,
        sequence=actor._state.sequence,
    )


@router.patch("/{room_id}/plan", response_model=CommandEditPlanResponse)
async def update_plan_frontend(
    room_id: str,
    request: PlanUpdateRequest,
    current_user: User = Depends(require_editor),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandEditPlanResponse:
    """
    Update the plan (frontend-compatible endpoint).
    Uses the same logic as edit-plan but with frontend-friendly path/body.
    """
    # Convert items to edits format
    edits = []
    for item in request.items:
        if "id" not in item:
            # New item
            edits.append({"type": "add", "item": item})
        else:
            # Check if item exists
            existing_items = await actor.plan.get_items()
            existing = next((i for i in existing_items if i["id"] == item["id"]), None)
            if existing:
                # Update existing item
                changes = {k: v for k, v in item.items() if k != "id"}
                edits.append({"type": "update", "item_id": item["id"], "changes": changes})
            else:
                # Add new item with specific ID
                edits.append({"type": "add", "item": item})

    await actor.command_edit_plan(edits, current_user.id)
    return CommandEditPlanResponse(
        sequence=actor._state.sequence,
        edits_applied=len(edits),
    )


@router.post("/{room_id}/plan/approve", response_model=CommandApprovePlanResponse)
async def approve_plan_frontend(
    room_id: str,
    request: PlanApproveRequest,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandApprovePlanResponse:
    """
    Approve plan items (frontend-compatible endpoint).
    """
    await actor.approve_plan_items(request.plan_item_ids, current_user.id)
    return CommandApprovePlanResponse(
        sequence=actor._state.sequence,
        approved_items=request.plan_item_ids,
    )


@router.post("/{room_id}/conflicts/{conflict_id}/vote", response_model=CommandVoteResponse)
async def vote_on_conflict_frontend(
    room_id: str,
    conflict_id: str,
    request: ConflictVoteRequest,
    current_user: User = Depends(require_editor),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandVoteResponse:
    """
    Vote on a conflict (frontend-compatible endpoint).
    """
    await actor.command_vote(
        option_id=request.option_id,
        issued_by=current_user.id,
        vote_value=request.vote_value,
        plan_item_id=request.plan_item_id,
    )
    return CommandVoteResponse(sequence=actor._state.sequence)


@router.post("/{room_id}/conflicts/{conflict_id}/override", response_model=CommandOverrideResponse)
async def override_conflict_frontend(
    room_id: str,
    conflict_id: str,
    request: ConflictOverrideRequest,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandOverrideResponse:
    """
    Override a conflict (frontend-compatible endpoint).
    """
    await actor.command_override(
        new_plan=request.new_plan,
        issued_by=current_user.id,
        reason=request.reason,
    )
    return CommandOverrideResponse(sequence=actor._state.sequence)


@router.post("/{room_id}/questions/{question_id}/answer", response_model=CommandAnswerQuestionResponse)
async def answer_question_frontend(
    room_id: str,
    question_id: str,
    request: QuestionAnswerRequest,
    current_user: User = Depends(require_editor),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandAnswerQuestionResponse:
    """
    Answer a question (frontend-compatible endpoint).
    """
    await actor.command_answer_question(
        question_id=request.question_id,
        answer=request.answer,
        issued_by=current_user.id,
    )
    return CommandAnswerQuestionResponse(sequence=actor._state.sequence)


# =============================================================================
# File Endpoints (Frontend-Compatible - path in body)
# =============================================================================

@router.post("/{room_id}/files/lock", response_model=FileLockResponse)
async def lock_file_frontend(
    room_id: str,
    request: FileLockRequest,
    current_user: User = Depends(require_editor),
    actor: RoomActor = Depends(get_room_actor),
) -> FileLockResponse:
    """
    Lock a file for editing (frontend-compatible with path in body).
    """
    path = request.path.lstrip("/")
    locked = await actor.lock_file(path, current_user.id)
    locked_by = await actor.locked_by(path) if locked else None

    return FileLockResponse(
        path=path,
        locked=locked,
        locked_by=locked_by,
        sequence=actor._state.sequence,
    )


@router.post("/{room_id}/files/unlock", response_model=FileUnlockResponse)
async def unlock_file_frontend(
    room_id: str,
    request: FileUnlockRequest,
    current_user: User = Depends(require_editor),
    actor: RoomActor = Depends(get_room_actor),
) -> FileUnlockResponse:
    """
    Unlock a file (frontend-compatible with path in body).
    """
    path = request.path.lstrip("/")

    # Check if user can unlock
    locked_by = await actor.locked_by(path)
    if locked_by and locked_by != current_user.id:
        # Check if current user is owner
        if current_user.id != actor.owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the lock holder or room owner can unlock"
            )

    unlocked = await actor.unlock_file(path, current_user.id)

    return FileUnlockResponse(
        path=path,
        unlocked=unlocked,
        sequence=actor._state.sequence,
    )


@router.put("/{room_id}/files", response_model=FileUpdateResponse)
async def update_file_frontend(
    room_id: str,
    request: FileUpdateRequestFrontend,
    current_user: User = Depends(require_editor),
    actor: RoomActor = Depends(get_room_actor),
) -> FileUpdateResponse:
    """
    Update a file (frontend-compatible with path in body).
    """
    path = request.path.lstrip("/")

    # Check if locked by another user
    if await actor.is_locked(path):
        locked_by = await actor.locked_by(path)
        if locked_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"File is locked by another user: {locked_by}"
            )

    await actor.update_file(path, request.content, current_user.id)

    entry = actor.manifest.get_entry(path)

    return FileUpdateResponse(
        file_id=entry.file_id if entry else "",
        path=path,
        size=entry.size if entry else len(request.content.encode()),
        sequence=actor._state.sequence,
    )


@router.delete("/{room_id}/files/{file_path:path}", response_model=FileDeleteResponse)
async def delete_file_frontend(
    room_id: str,
    file_path: str,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> FileDeleteResponse:
    """
    Delete a file (frontend-compatible with path as path parameter).
    """
    path = file_path.lstrip("/")

    # Check if file exists
    content = await actor.get_file(path)
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {path}"
        )

    await actor.delete_file(path, current_user.id)

    return FileDeleteResponse(
        path=path,
        sequence=actor._state.sequence,
        deleted=True,
    )


@router.post("/{room_id}/rewind", response_model=CommandRewindResponse)
async def rewind_frontend(
    room_id: str,
    request: RewindRequest,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandRewindResponse:
    """
    Rewind room state to a checkpoint (frontend-compatible with checkpoint_id).
    """
    # Get the checkpoint to find its sequence
    checkpoint_data = actor.manifest.get_checkpoint(request.checkpoint_id)
    if not checkpoint_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checkpoint not found: {request.checkpoint_id}"
        )

    target_sequence = checkpoint_data.get("sequence", 0)

    success = await actor.rewind_to_sequence(
        target_sequence=target_sequence,
        user_id=current_user.id,
        reason=f"Rewind to checkpoint {request.checkpoint_id}",
        preserve_checkpoint=True,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rewind failed: no events found or invalid target sequence"
        )
    return CommandRewindResponse(
        sequence=actor._state.sequence,
        target_sequence=target_sequence,
    )


@router.patch("/{room_id}/budget", response_model=CommandRaiseBudgetResponse)
async def update_budget_frontend(
    room_id: str,
    request: BudgetUpdateRequest,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandRaiseBudgetResponse:
    """
    Update budget caps (frontend-compatible endpoint).
    """
    budget_status = await actor.budget.get_status()
    was_paused = budget_status["paused"]

    success = await actor.raise_budget_caps(
        user_id=current_user.id,
        token_cap=request.tokens_cap,
        sandbox_run_cap=request.runs_cap,
    )
    if not success:
        # require_owner already passed, so a False here means the caps were not raised
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New caps must be higher than the current caps"
        )

    new_status = await actor.budget.get_status()
    resumed = was_paused and not new_status["paused"]

    return CommandRaiseBudgetResponse(
        sequence=actor._state.sequence,
        token_cap=request.tokens_cap,
        sandbox_run_cap=request.runs_cap,
        resumed=resumed,
    )