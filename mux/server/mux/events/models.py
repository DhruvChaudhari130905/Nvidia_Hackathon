"""Pydantic event models. Exported to JSON Schema, and TypeScript types are generated from them."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Any

RoomId = UUID
Permission = Literal["owner", "editor", "viewer"]
MemberPermission = Literal["editor", "viewer"] #what can be granted: the owner is set when the room is created
DomainRole = Literal["pm", "design", "eng"]
LinkAccess = Literal["restricted", "anyone"]
MessageTo = Literal["agent", "team"]
PlanStatus = Literal["draft", "todo", "doing", "done", "skipped_conflict", "skipped_question"]
Tab = Literal["feed", "preview", "code", "cards"]
BudgetLimit = Literal["tokens", "runs"]
# The coordinator's labels, plus "plan": the first message to a room with no plan drafts one
MessageLabel = Literal["merge", "queue", "interrupt", "conflict", "chat", "plan"]
ConflictDomain = Literal["ui", "architecture", "scope"]

EXEMPT_TYPES: frozenset[str] = frozenset({
    "room.created", "sharing.changed", "budget.updated", "room.paused", "room.resumed",
    "room.rewound", "checkpoint.created", "message.posted", "sitting.ended",
})

EXEMPT_PREFIXES = ("member.", "export.")


def is_exempt(type: str) -> bool:
    """True if events of this type are never greyed out."""
    return type in EXEMPT_TYPES or type.startswith(EXEMPT_PREFIXES)


class EventEnvelope(BaseModel):
    """Wire/storage shape of every event."""
    seq: int
    type: str
    ts: datetime
    room_id: RoomId
    actor: str
    payload: dict


class Payload(BaseModel):
    """Payload contract: unknown fields are an error, so the Python and TS shapes can't drift silently."""
    model_config = ConfigDict(extra="forbid")


class FileChanged(Payload):
    """Payload of 'file.changed'."""

    path: str
    hash: str | None
    version: int
    base_version: int | None
    deleted: bool
    actor: str
    diff_summary: str


class CheckpointCreated(Payload):
    """Payload of 'checkpoint.created'. The checkpoint's own seq is the envelope seq (R4)."""

    checkpoint_id: UUID
    parent_id: UUID | None
    start_seq: int
    manifest_id: UUID
    sandbox_snapshot_uuid: str | None


class RoomRewound(Payload):
    """Payload of 'room.rewound' (R2): the new version of every path whose content changed, applied as given.
       Paths missing from the target checkpoint's manifest are removed; they keep their high-water marks."""
    checkpoint_id: UUID
    versions: dict[str, int]


class RoomCreated(Payload):
    """Payload of 'room.created'."""

    owner_id: UUID
    title: str
    description: str


class MemberJoined(Payload):
    """Payload of 'member.joined'."""

    user_id: UUID
    permission: MemberPermission
    domain_role: DomainRole | None


class MemberRoleChanged(Payload):
    """Payload of 'member.role_changed'."""

    user_id: UUID
    permission: MemberPermission


class SharingChanged(Payload):
    """Payload of 'sharing.changed'. link_permission is None when link_access is 'restricted'."""

    link_access: LinkAccess
    link_permission: MemberPermission | None


class MessagePosted(Payload):
    """Payload of 'message.posted'."""

    id: UUID
    user_id: UUID
    text: str
    to: MessageTo


class MessageLabeled(Payload):
    """Payload of 'message.labeled': what the coordinator decided for one message to the agent."""

    message_id: UUID
    label: MessageLabel
    rationale: str
    domain: ConflictDomain | None = None
    fallback: bool = False  # True when the model failed twice and the message was queued as is
    task_id: str | None = None  # the task a queue, merge or interrupt went into


class CoordinatorReply(Payload):
    """Payload of 'coordinator.reply'."""

    text: str
    message_id: UUID | None = None  # the message it answers


class ConflictOpened(Payload):
    """Payload of 'conflict.opened'. `task_ids` are the tasks held (skipped_conflict) until the vote closes."""

    id: UUID
    message_ids: list[UUID]
    summary: str
    options: list[str] = Field(min_length=2, max_length=4)
    domain: ConflictDomain
    task_ids: list[str]


class EvidenceCitation(Payload):
    title: str
    url: str


class ConflictEvidence(Payload):
    """Payload of 'conflict.evidence': the research (None when there was none), and the vote opens until expires_at."""

    conflict_id: UUID
    summary: str | None = None
    citations: list[EvidenceCitation] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    expires_at: datetime


class ConflictVote(Payload):
    """Payload of 'conflict.vote'. A later vote by the same user replaces the earlier one."""

    conflict_id: UUID
    user_id: UUID
    option: str
    weight: int


class ConflictClosed(Payload):
    """Payload of 'conflict.closed'. resolved_by: "votes", "owner" or "domain" (the tie rules), or "override"."""

    conflict_id: UUID
    result: str
    resolved_by: str
    totals: dict[str, int]


class QuestionOpened(Payload):
    """Payload of 'question.opened': the coder asks the room. Its task is skipped_question until an answer."""

    id: UUID
    task_id: str | None
    text: str
    options: list[str] = Field(min_length=2)
    default: str
    expires_at: datetime


class QuestionAnswered(Payload):
    """Payload of 'question.answered'."""

    question_id: UUID
    answer: str
    user_id: UUID


class QuestionDefaulted(Payload):
    """Payload of 'question.defaulted': nobody answered in time, so the default is the answer."""

    question_id: UUID
    answer: str


class PlanItem(Payload):
    """One task of the plan. Also the payload of 'plan.item_added'."""

    id: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    status: PlanStatus = "draft"
    owner_role: DomainRole | None = None
    notes: str | None = None
    merged_notes: list[str] = Field(default_factory=list)


class PlanItems(Payload):
    """Payload of 'plan.drafted' and 'plan.edited': the whole plan, in order."""

    items: list[PlanItem]


class PlanItemUpdated(Payload):
    """Payload of 'plan.item_updated'. `changes` holds only the fields that change."""

    id: str
    changes: dict[str, Any]


class TaskRef(Payload):
    """Payload of 'task.started' and 'task.finished'."""

    task_id: str


class FileLockChanged(Payload):
    """Payload of 'file.locked' and 'file.unlocked'. `user_id` is the lock's holder."""

    path: str
    user_id: UUID


class BudgetUpdated(Payload):
    """Payload of 'budget.updated'. Field names match the web app's Budget type."""

    tokens_used: int
    runs_used: int
    tokens_cap: int
    runs_cap: int


class RoomPaused(Payload):
    """Payload of 'room.paused': which cap was reached. 'room.resumed' has an empty payload."""

    reason: BudgetLimit


class SittingEnded(Payload):
    """Payload of 'sitting.ended': nobody connected for 30 minutes, or the owner ended the session."""

    reason: Literal["idle", "owner"]


class PresenceJoined(Payload):
    """Payload of 'presence.join' (broadcast, never stored)."""

    user_id: UUID
    name: str | None
    tab: Tab | None
    typing: bool


class PresenceLeft(Payload):
    """Payload of 'presence.leave' (broadcast, never stored)."""

    user_id: UUID


class PresenceTyping(Payload):
    """Payload of 'presence.typing' (broadcast, never stored)."""

    user_id: UUID
    typing: bool


class PresenceTab(Payload):
    """Payload of 'presence.tab' (broadcast, never stored)."""

    user_id: UUID
    tab: Tab
