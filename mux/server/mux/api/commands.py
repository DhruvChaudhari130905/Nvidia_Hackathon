"""Room commands over REST: steer, vote, override, approve plan, edit plan, answer question, rewind, end session. Each returns the accepted event seq."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from mux.api.deps import get_room_actor_dep, get_current_user, require_editor, require_owner, require_viewer, User
from mux.rooms.actor import RoomActor

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class CommandSteerRequest(BaseModel):
    """Request to steer the coder."""
    instructions: str = Field(..., min_length=1, max_length=5000, description="Natural language steering instructions")
    parameters: Optional[dict] = Field(None, description="Additional parameters (model hints, etc.)")


class CommandSteerResponse(BaseModel):
    """Response after steering."""
    sequence: int
    event_type: str = "command_steer"


class CommandVoteRequest(BaseModel):
    """Request to vote on an option."""
    option_id: str = Field(..., description="ID of option being voted for")
    vote_value: Any = Field(..., description="Vote value (bool, int, or string)")
    plan_item_id: Optional[str] = Field(None, description="Specific plan item being voted on")


class CommandVoteResponse(BaseModel):
    """Response after voting."""
    sequence: int
    event_type: str = "command_vote"


class CommandOverrideRequest(BaseModel):
    """Request to override the plan."""
    new_plan: list[dict] = Field(..., description="New plan to replace current one")
    reason: Optional[str] = Field(None, description="Reason for override")


class CommandOverrideResponse(BaseModel):
    """Response after override."""
    sequence: int
    event_type: str = "command_override"


class CommandApprovePlanRequest(BaseModel):
    """Request to approve plan items."""
    plan_item_ids: list[str] = Field(..., min_length=1, description="IDs of plan items to approve")
    approval_note: Optional[str] = Field(None, description="Optional note about approval")


class CommandApprovePlanResponse(BaseModel):
    """Response after approving plan."""
    sequence: int
    event_type: str = "command_approve_plan"
    approved_items: list[str]


class CommandEditPlanRequest(BaseModel):
    """Request to edit the plan."""
    edits: list[dict] = Field(..., min_length=1, description="List of edits to apply")
    # Each edit: {"type": "add|update|remove|complete", "item": {...}, "item_id": "...", "changes": {...}}


class CommandEditPlanResponse(BaseModel):
    """Response after editing plan."""
    sequence: int
    event_type: str = "command_edit_plan"
    edits_applied: int


class CommandAnswerQuestionRequest(BaseModel):
    """Request to answer a question."""
    question_id: str = Field(..., description="ID of the question being answered")
    answer: str = Field(..., min_length=1, max_length=10000, description="The answer text")


class CommandAnswerQuestionResponse(BaseModel):
    """Response after answering question."""
    sequence: int
    event_type: str = "command_answer_question"


class CommandRewindRequest(BaseModel):
    """Request to rewind the room."""
    target_sequence: int = Field(..., ge=0, description="Event sequence number to rewind to")
    reason: Optional[str] = Field(None, description="Reason for rewinding")
    preserve_checkpoint: bool = Field(False, description="Whether to create checkpoint before rewind")


class CommandRewindResponse(BaseModel):
    """Response after rewinding."""
    sequence: int
    event_type: str = "command_rewind"
    target_sequence: int


class CommandEndSessionRequest(BaseModel):
    """Request to end the session."""
    reason: Optional[str] = Field(None, description="Reason for ending session")
    cleanup_data: bool = Field(True, description="Whether to cleanup temporary data")


class CommandEndSessionResponse(BaseModel):
    """Response after ending session."""
    sequence: int
    event_type: str = "command_end_session"
    ended: bool


class CommandRaiseBudgetRequest(BaseModel):
    """Request to raise budget caps."""
    token_cap: Optional[int] = Field(None, ge=1, description="New token cap")
    sandbox_run_cap: Optional[int] = Field(None, ge=1, description="New sandbox run cap")


class CommandRaiseBudgetResponse(BaseModel):
    """Response after raising budget caps."""
    sequence: int
    event_type: str = "command_raise_budget"
    token_cap: Optional[int]
    sandbox_run_cap: Optional[int]
    resumed: bool


class CommandForceResumeResponse(BaseModel):
    """Response after forcing budget resume."""
    sequence: int
    event_type: str = "command_force_resume"
    resumed: bool


# =============================================================================
# Helper: Get RoomActor for a room
# =============================================================================

# Shared dependency: looks up (or rehydrates) an existing room; never creates one.
get_room_actor = get_room_actor_dep


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/{room_id}/steer", response_model=CommandSteerResponse)
async def command_steer(
    room_id: str,
    request: CommandSteerRequest,
    current_user: User = Depends(require_editor),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandSteerResponse:
    """
    Issue a steer command to guide the coder.
    Requires editor permission.
    """
    await actor.command_steer(
        instructions=request.instructions,
        issued_by=current_user.id,
        parameters=request.parameters,
    )
    return CommandSteerResponse(sequence=actor._state.sequence)


@router.post("/{room_id}/vote", response_model=CommandVoteResponse)
async def command_vote(
    room_id: str,
    request: CommandVoteRequest,
    current_user: User = Depends(require_editor),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandVoteResponse:
    """
    Issue a vote command.
    Requires editor permission.
    """
    await actor.command_vote(
        option_id=request.option_id,
        issued_by=current_user.id,
        vote_value=request.vote_value,
        plan_item_id=request.plan_item_id,
    )
    return CommandVoteResponse(sequence=actor._state.sequence)


@router.post("/{room_id}/override", response_model=CommandOverrideResponse)
async def command_override(
    room_id: str,
    request: CommandOverrideRequest,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandOverrideResponse:
    """
    Override the current plan entirely (owner only).
    """
    await actor.command_override(
        new_plan=request.new_plan,
        issued_by=current_user.id,
        reason=request.reason,
    )
    return CommandOverrideResponse(sequence=actor._state.sequence)


@router.post("/{room_id}/approve-plan", response_model=CommandApprovePlanResponse)
async def command_approve_plan(
    room_id: str,
    request: CommandApprovePlanRequest,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandApprovePlanResponse:
    """
    Approve draft plan items (owner only).
    """
    await actor.approve_plan_items(request.plan_item_ids, current_user.id)
    return CommandApprovePlanResponse(
        sequence=actor._state.sequence,
        approved_items=request.plan_item_ids,
    )


@router.post("/{room_id}/edit-plan", response_model=CommandEditPlanResponse)
async def command_edit_plan(
    room_id: str,
    request: CommandEditPlanRequest,
    current_user: User = Depends(require_editor),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandEditPlanResponse:
    """
    Apply a list of edits to the plan.
    Requires editor permission.
    """
    await actor.command_edit_plan(request.edits, current_user.id)
    return CommandEditPlanResponse(
        sequence=actor._state.sequence,
        edits_applied=len(request.edits),
    )


@router.post("/{room_id}/answer-question", response_model=CommandAnswerQuestionResponse)
async def command_answer_question(
    room_id: str,
    request: CommandAnswerQuestionRequest,
    current_user: User = Depends(require_editor),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandAnswerQuestionResponse:
    """
    Answer a question in the room.
    Requires editor permission.
    """
    await actor.command_answer_question(
        question_id=request.question_id,
        answer=request.answer,
        issued_by=current_user.id,
    )
    return CommandAnswerQuestionResponse(sequence=actor._state.sequence)


@router.post("/{room_id}/rewind", response_model=CommandRewindResponse)
async def command_rewind(
    room_id: str,
    request: CommandRewindRequest,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandRewindResponse:
    """
    Rewind room state to a specific event sequence (owner only).
    """
    success = await actor.rewind_to_sequence(
        target_sequence=request.target_sequence,
        user_id=current_user.id,
        reason=request.reason,
        preserve_checkpoint=request.preserve_checkpoint,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rewind failed: no events found or invalid target sequence"
        )
    return CommandRewindResponse(
        sequence=actor._state.sequence,
        target_sequence=request.target_sequence,
    )


@router.post("/{room_id}/end-session", response_model=CommandEndSessionResponse)
async def command_end_session(
    room_id: str,
    request: CommandEndSessionRequest,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandEndSessionResponse:
    """
    End the current session (owner only).
    """
    ended = await actor.command_end_session(
        issued_by=current_user.id,
        reason=request.reason,
        cleanup_data=request.cleanup_data,
    )
    if not ended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the room owner can end the session"
        )
    return CommandEndSessionResponse(
        sequence=actor._state.sequence,
        ended=True,
    )


@router.post("/{room_id}/raise-budget", response_model=CommandRaiseBudgetResponse)
async def command_raise_budget(
    room_id: str,
    request: CommandRaiseBudgetRequest,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandRaiseBudgetResponse:
    """
    Raise budget caps (owner only).
    If room was paused and new caps cover usage, auto-resumes.
    """
    budget_status = await actor.budget.get_status()
    was_paused = budget_status["paused"]

    success = await actor.raise_budget_caps(
        user_id=current_user.id,
        token_cap=request.token_cap,
        sandbox_run_cap=request.sandbox_run_cap,
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
        token_cap=request.token_cap,
        sandbox_run_cap=request.sandbox_run_cap,
        resumed=resumed,
    )


@router.post("/{room_id}/force-resume", response_model=CommandForceResumeResponse)
async def command_force_resume(
    room_id: str,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> CommandForceResumeResponse:
    """
    Force resume budget without raising caps (owner only).
    """
    success = await actor.force_budget_resume(current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the room owner can force resume budget"
        )
    return CommandForceResumeResponse(
        sequence=actor._state.sequence,
        resumed=True,
    )


# =============================================================================
# Budget & Status Query Endpoints (read-only)
# =============================================================================

class BudgetStatusResponse(BaseModel):
    """Budget status snapshot."""
    tokens_used: int
    token_cap: int
    token_pct: float
    sandbox_runs_used: int
    sandbox_run_cap: int
    sandbox_run_pct: float
    paused: bool
    paused_reason: Optional[str]
    paused_at: Optional[float]


@router.get("/{room_id}/budget", response_model=BudgetStatusResponse)
async def get_budget_status(
    room_id: str,
    current_user: User = Depends(require_viewer),
    actor: RoomActor = Depends(get_room_actor),
) -> BudgetStatusResponse:
    """Get current budget status."""
    status = await actor.get_budget_status()
    return BudgetStatusResponse(**status)


@router.get("/{room_id}/checkpoints")
async def list_checkpoints(
    room_id: str,
    current_user: User = Depends(require_viewer),
    actor: RoomActor = Depends(get_room_actor),
) -> dict:
    """List available checkpoints for rewind."""
    checkpoints = actor.manifest.list_checkpoints()
    return {"checkpoints": checkpoints}