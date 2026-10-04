"""Pydantic event models. Exported to JSON Schema, and TypeScript types are generated from them."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from typing import Literal

RoomId = UUID
Permission = Literal["owner", "editor", "viewer"]
MemberPermission = Literal["editor", "viewer"] #what can be granted: the owner is set when the room is created
DomainRole = Literal["pm", "design", "eng"]
LinkAccess = Literal["restricted", "anyone"]
MessageTo = Literal["agent", "team"]

EXEMPT_TYPES: frozenset[str] = frozenset({
    "room.created", "sharing.changed", "budget.updated", "room.paused", "room.resumed",
    "room.rewound", "checkpoint.created", "message.posted",
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
    