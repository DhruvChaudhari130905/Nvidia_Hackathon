"""Room REST API at /api/rooms. Every change goes through the room's actor, which stores it as an event and
broadcasts it on the room's WebSocket, so responses carry only what the caller needs right away.

Errors: a broken rule is 400 (ValueError), a lock or state conflict 409 (PermissionError), a missing
file or checkpoint 404 (KeyError); main.py maps them."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from mux.api.deps import Actor, Editor, Owner, RoomAccess, User, Viewer
from mux.checkpoints.checkpoint import CheckpointRow
from mux.events.models import (
    ConflictDomain, DomainRole, EvidenceCitation, LinkAccess, MemberPermission, MessagePosted, MessageTo, Permission,
    PlanItem,
)
from mux.rooms import budget as budgets
from mux.rooms import records
from mux.rooms.cards import Conflict, Question
from mux.rooms.registry import get_registry

router = APIRouter()

# Size limits on what people send; the events and the coder's context would carry anything larger
DESCRIPTION_CHARS = 4000
NOTES_CHARS = 2000
PLAN_ITEMS = 100
FILE_CHARS = 1_000_000
CHOICE_CHARS = 500


# ---- rooms ----

class RoomIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=DESCRIPTION_CHARS)
    domain_role: DomainRole | None = None


class MemberOut(BaseModel):
    user_id: UUID
    permission: Permission
    domain_role: DomainRole | None


class RoomOut(BaseModel):
    """A room's settings and members. The plan, files and feed come from the WebSocket's events."""

    id: UUID
    owner_id: UUID
    title: str
    description: str
    link_access: LinkAccess
    link_permission: MemberPermission | None
    head_checkpoint_id: UUID | None
    my_permission: Permission
    members: list[MemberOut]
    last_seq: int  # events up to here are history; the WebSocket's later events are live
    budget_tokens_cap: int
    budget_runs_cap: int


class RoomListItem(BaseModel):
    id: UUID
    title: str
    description: str
    permission: Permission
    created_at: datetime
    members: list[MemberOut]
    budget_tokens_cap: int
    budget_runs_cap: int


def room_out(access: RoomAccess) -> RoomOut:
    record = access.actor.record
    return RoomOut(
        id=record.id, owner_id=record.owner_id, title=record.title, description=record.description,
        link_access=record.link_access, link_permission=record.link_permission,
        head_checkpoint_id=record.head_checkpoint_id, my_permission=access.permission,
        members=[
            MemberOut(user_id=user_id, permission=m.permission, domain_role=m.domain_role)
            for user_id, m in record.members.items()
        ],
        last_seq=access.actor.emitter.seq,
        budget_tokens_cap=access.actor.budget.tokens_cap, budget_runs_cap=access.actor.budget.runs_cap,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_room(body: RoomIn, user: User) -> RoomOut:
    actor = await get_registry().create(user.id, body.title, description=body.description, domain_role=body.domain_role)
    return room_out(RoomAccess(actor, user, "owner"))


@router.get("")
async def list_rooms(user: User) -> list[RoomListItem]:
    """The rooms the caller is a member of, newest first."""
    async with get_registry().session() as s:
        rooms = await records.list_for_user(user.id, session=s)
    return [
        RoomListItem(
            id=r.id, title=r.title, description=r.description, permission=r.permission, created_at=r.created_at,
            members=[MemberOut(user_id=u, permission=m.permission, domain_role=m.domain_role) for u, m in r.members.items()],
            budget_tokens_cap=r.tokens_cap or budgets.DEFAULT_TOKENS_CAP,
            budget_runs_cap=r.runs_cap or budgets.DEFAULT_RUNS_CAP,
        )
        for r in rooms
    ]


@router.get("/{room_id}")
async def get_room(access: Viewer) -> RoomOut:
    return room_out(access)


# ---- members and sharing ----

class JoinIn(BaseModel):
    domain_role: DomainRole | None = None


class JoinOut(BaseModel):
    permission: Permission


@router.post("/{room_id}/join")
async def join_room(user: User, actor: Actor, body: JoinIn | None = None) -> JoinOut:
    """Open a room by its link. A member gets their permission back; 403 for a private room."""
    try:
        permission = await actor.join(user.id, body.domain_role if body else None)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from e
    return JoinOut(permission=permission)


class MemberIn(BaseModel):
    permission: MemberPermission
    domain_role: DomainRole | None = None


@router.put("/{room_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def set_member(user_id: UUID, body: MemberIn, access: Owner) -> None:
    await access.actor.set_member(user_id, body.permission, access.user.id, body.domain_role)


class SharingIn(BaseModel):
    link_access: LinkAccess
    link_permission: MemberPermission | None = None


@router.put("/{room_id}/sharing", status_code=status.HTTP_204_NO_CONTENT)
async def set_sharing(body: SharingIn, access: Owner) -> None:
    await access.actor.set_sharing(body.link_access, body.link_permission, access.user.id)


# ---- messages and the plan ----

class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    to: MessageTo = "agent"


@router.post("/{room_id}/messages", status_code=status.HTTP_201_CREATED)
async def post_message(body: MessageIn, access: Editor) -> MessagePosted:
    return await access.actor.post_message(access.user.id, body.text, body.to)


class PlanIn(BaseModel):
    items: list[PlanItem] = Field(max_length=PLAN_ITEMS)


def _check_notes(item: PlanItem) -> PlanItem:
    if item.notes is not None and len(item.notes) > NOTES_CHARS:
        raise ValueError(f"task notes are limited to {NOTES_CHARS} characters")
    return item


class PlanItemPatch(BaseModel):
    """What a person may change on one task. Setting status back to todo retries a blocked or skipped task;
    the coder and the coordinator move tasks through the other statuses."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=1, max_length=200)
    notes: str | None = Field(None, max_length=NOTES_CHARS)
    owner_role: DomainRole | None = None
    status: Literal["todo"] | None = None


@router.put("/{room_id}/plan", status_code=status.HTTP_204_NO_CONTENT)
async def edit_plan(body: PlanIn, access: Editor) -> None:
    """Replace the whole plan (the plan editor)."""
    await access.actor.edit_plan([_check_notes(item) for item in body.items], str(access.user.id))


@router.post("/{room_id}/plan/approve", status_code=status.HTTP_204_NO_CONTENT)
async def approve_plan(access: Owner) -> None:
    await access.actor.approve_plan(str(access.user.id))


@router.post("/{room_id}/plan/items", status_code=status.HTTP_204_NO_CONTENT)
async def add_plan_item(item: PlanItem, access: Editor) -> None:
    if len(access.actor.plan) >= PLAN_ITEMS:
        raise ValueError(f"a plan has at most {PLAN_ITEMS} tasks")
    await access.actor.add_plan_item(_check_notes(item), str(access.user.id))


@router.patch("/{room_id}/plan/items/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_plan_item(task_id: str, body: PlanItemPatch, access: Editor) -> None:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise ValueError("nothing to change")
    if None in (changes.get("title", ""), changes.get("status", "")):
        raise ValueError("title and status cannot be empty")
    await access.actor.update_plan_item(task_id, changes, str(access.user.id))


# ---- conflict and question cards ----

class ConflictOut(BaseModel):
    id: UUID
    message_ids: list[UUID]
    summary: str
    options: list[str]
    domain: ConflictDomain
    task_ids: list[str]
    opened_at: datetime
    expires_at: datetime | None  # None while the research runs
    evidence: str | None
    citations: list[EvidenceCitation]
    votes: dict[UUID, str]
    result: str | None
    resolved_by: str | None


class QuestionOut(BaseModel):
    id: UUID
    task_id: str | None
    text: str
    options: list[str]
    default: str
    expires_at: datetime
    answer: str | None
    defaulted: bool


class CardsOut(BaseModel):
    conflicts: list[ConflictOut]
    questions: list[QuestionOut]


def conflict_out(c: Conflict) -> ConflictOut:
    return ConflictOut(
        id=c.id, message_ids=c.message_ids, summary=c.summary, options=c.options, domain=c.domain,
        task_ids=c.task_ids, opened_at=c.opened_at, expires_at=c.expires_at, evidence=c.evidence,
        citations=c.citations, votes=c.votes, result=c.result, resolved_by=c.resolved_by,
    )


def question_out(q: Question) -> QuestionOut:
    return QuestionOut(
        id=q.id, task_id=q.task_id, text=q.text, options=q.options, default=q.default,
        expires_at=q.expires_at, answer=q.answer, defaulted=q.defaulted,
    )


class OptionIn(BaseModel):
    option: str = Field(max_length=CHOICE_CHARS)


class AnswerIn(BaseModel):
    answer: str = Field(max_length=CHOICE_CHARS)


@router.get("/{room_id}/cards")
async def list_cards(access: Viewer) -> CardsOut:
    """Every conflict and question of the room, oldest first; open ones have no result or answer yet."""
    cards = access.actor.cards
    return CardsOut(
        conflicts=[conflict_out(c) for c in cards.conflicts.values()],
        questions=[question_out(q) for q in cards.questions.values()],
    )


@router.post("/{room_id}/conflicts/{conflict_id}/vote", status_code=status.HTTP_204_NO_CONTENT)
async def vote(conflict_id: UUID, body: OptionIn, access: Editor) -> None:
    await access.actor.vote(conflict_id, access.user.id, body.option)


@router.post("/{room_id}/conflicts/{conflict_id}/override", status_code=status.HTTP_204_NO_CONTENT)
async def override(conflict_id: UUID, body: OptionIn, access: Owner) -> None:
    await access.actor.override(conflict_id, body.option, access.user.id)


@router.post("/{room_id}/questions/{question_id}/answer", status_code=status.HTTP_204_NO_CONTENT)
async def answer_question(question_id: UUID, body: AnswerIn, access: Editor) -> None:
    await access.actor.answer_question(question_id, body.answer, access.user.id)


# ---- files and locks ----

class FileEntry(BaseModel):
    path: str
    version: int


class FileOut(BaseModel):
    path: str
    version: int
    content: str


class SaveIn(BaseModel):
    content: str | None = Field(max_length=FILE_CHARS)  # None deletes the file
    base_version: int | None  # the version the edit started from; None for a new file


class SaveOut(BaseModel):
    path: str
    version: int | None  # None once deleted
    changed: bool


@router.get("/{room_id}/files")
async def list_files(access: Viewer) -> list[FileEntry]:
    manifest = access.actor.files.live.manifest
    return [FileEntry(path=path, version=entry.version) for path, entry in sorted(manifest.items())]


@router.get("/{room_id}/files/{path:path}")
async def read_file(path: str, access: Viewer) -> FileOut:
    data, version = await access.actor.read_file(path)
    try:
        content = data.decode()
    except UnicodeDecodeError as e:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"{path} is not a text file") from e
    return FileOut(path=path, version=version, content=content)


@router.put("/{room_id}/files/{path:path}")
async def save_file(path: str, body: SaveIn, access: Editor) -> SaveOut:
    """Save a manual edit. The caller must hold the file's lock. 409 with the current version if
    base_version is stale."""
    content = body.content.encode() if body.content is not None else None
    result = await access.actor.save_file(path, content, body.base_version, access.user.id)
    if not result.ok:
        detail = {"message": "the file changed since base_version", "version": result.version}
        raise HTTPException(status.HTTP_409_CONFLICT, detail)
    return SaveOut(path=result.path, version=result.version, changed=result.changed)


@router.post("/{room_id}/locks/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
async def lock_file(path: str, access: Editor) -> None:
    """Take or refresh the soft lock. 409 if someone else holds it."""
    await access.actor.lock_file(path, access.user.id)


@router.delete("/{room_id}/locks/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
async def unlock_file(path: str, access: Editor) -> None:
    """Release the lock. The owner can release anyone's."""
    await access.actor.unlock_file(path, access.user.id, force=access.permission == "owner")


# ---- checkpoints and rewind ----

class CheckpointOut(BaseModel):
    id: UUID
    seq: int
    parent_id: UUID | None
    created_at: datetime | None
    head: bool


class RewindIn(BaseModel):
    checkpoint_id: UUID


class RewindOut(BaseModel):
    checkpoint_id: UUID
    log: str | None  # the nearest task or day log on the path to the new head


def checkpoint_out(cp: CheckpointRow, access: RoomAccess) -> CheckpointOut:
    return CheckpointOut(
        id=cp.id, seq=cp.seq, parent_id=cp.parent_id, created_at=cp.created_at,
        head=cp.id == access.actor.record.head_checkpoint_id,
    )


@router.get("/{room_id}/checkpoints")
async def list_checkpoints(access: Viewer) -> list[CheckpointOut]:
    return [checkpoint_out(cp, access) for cp in sorted(access.actor.checkpoints.values(), key=lambda cp: cp.seq)]


@router.post("/{room_id}/checkpoints", status_code=status.HTTP_201_CREATED)
async def save_checkpoint(access: Editor) -> CheckpointOut:
    """Checkpoint the live files and plan now (the agent also does after every task)."""
    return checkpoint_out(await access.actor.save_checkpoint(str(access.user.id)), access)


@router.post("/{room_id}/rewind")
async def rewind(body: RewindIn, access: Owner) -> RewindOut:
    state = await access.actor.rewind_to(body.checkpoint_id, str(access.user.id))
    return RewindOut(checkpoint_id=state.checkpoint_id, log=state.log.body if state.log else None)


# ---- budget and sitting ----

class BudgetOut(BaseModel):
    tokens_used: int
    runs_used: int
    tokens_cap: int
    runs_cap: int
    paused: bool


class CapsIn(BaseModel):
    tokens_cap: int = Field(ge=1)
    runs_cap: int = Field(ge=1)


class EndOut(BaseModel):
    ended: bool  # False if no sitting was on


def budget_out(access: RoomAccess) -> BudgetOut:
    b = access.actor.budget
    return BudgetOut(
        tokens_used=b.tokens_used, runs_used=b.runs_used, tokens_cap=b.tokens_cap, runs_cap=b.runs_cap,
        paused=access.actor.paused,
    )


@router.get("/{room_id}/budget")
async def get_budget(access: Viewer) -> BudgetOut:
    return budget_out(access)


@router.put("/{room_id}/budget")
async def set_budget_caps(body: CapsIn, access: Owner) -> BudgetOut:
    await access.actor.set_budget_caps(body.tokens_cap, body.runs_cap, str(access.user.id))
    return budget_out(access)


@router.post("/{room_id}/session/end")
async def end_session(access: Owner) -> EndOut:
    return EndOut(ended=await access.actor.end_session(access.user.id))
