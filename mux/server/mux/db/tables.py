"""Tables: rooms, memberships, events, checkpoints, file blobs, manifests, task and day logs, conflicts, votes, questions, budgets, GitHub tokens."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Integer, LargeBinary, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _id() -> Mapped[UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid4)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Base(DeclarativeBase):
    pass


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[UUID] = _id()
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    link_access: Mapped[str] = mapped_column(Text, default="restricted")
    link_permission: Mapped[str | None] = mapped_column(Text)
    budget_tokens_cap: Mapped[int | None] = mapped_column(BigInteger)
    budget_runs_cap: Mapped[int | None] = mapped_column(Integer)
    # use_alter: rooms and checkpoints reference each other, so this FK is added after both exist.
    head_checkpoint_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("checkpoints.id", use_alter=True, name="fk_rooms_head_checkpoint_id")
    )
    created_at: Mapped[datetime] = _now()


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("permission in ('owner', 'editor', 'viewer')", name="ck_memberships_permission"),
        CheckConstraint("domain_role in ('pm', 'design', 'eng')", name="ck_memberships_domain_role"),
    )

    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    permission: Mapped[str] = mapped_column(Text)
    domain_role: Mapped[str | None] = mapped_column(Text)


class Event(Base):
    """Append-only (Q40): no `active` column; rewind's greying is computed from the checkpoint tree."""

    __tablename__ = "events"

    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()


class Blob(Base):
    __tablename__ = "blobs"

    hash: Mapped[str] = mapped_column(Text, primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    size: Mapped[int] = mapped_column(Integer)


class ManifestRow(Base):
    """Named `ManifestRow` so it does not clash with `mux.files.manifest.Manifest` (path -> Entry)."""

    __tablename__ = "manifests"

    id: Mapped[UUID] = _id()
    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    entries: Mapped[dict] = mapped_column(JSONB)


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id: Mapped[UUID] = _id()
    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    seq: Mapped[int] = mapped_column(BigInteger)  # seq of its own checkpoint.created event (R4)
    start_seq: Mapped[int] = mapped_column(BigInteger)
    manifest_id: Mapped[UUID] = mapped_column(ForeignKey("manifests.id"))
    sandbox_snapshot_uuid: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[list] = mapped_column(JSONB, default=list)
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("checkpoints.id"))
    created_at: Mapped[datetime] = _now()


class Log(Base):
    __tablename__ = "logs"
    __table_args__ = (CheckConstraint("kind in ('task', 'day')", name="ck_logs_kind"),)

    id: Mapped[UUID] = _id()
    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    pins: Mapped[list] = mapped_column(JSONB, default=list)
    checkpoint_id: Mapped[UUID] = mapped_column(ForeignKey("checkpoints.id"))
    # clock_timestamp(), not now(): now() is the transaction start, so two logs saved in one transaction
    # would tie and `rewind.head_state` could not tell which is newest.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class Conflict(Base):
    __tablename__ = "conflicts"

    id: Mapped[UUID] = _id()
    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id"))
    task_id: Mapped[str | None] = mapped_column(Text)  # plan item ids are strings like "t4"
    options: Mapped[list] = mapped_column(JSONB, default=list)
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    domain: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="open")
    result: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(Text)


class Vote(Base):
    __tablename__ = "votes"

    conflict_id: Mapped[UUID] = mapped_column(ForeignKey("conflicts.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    option: Mapped[str] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float, default=1.0)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[UUID] = _id()
    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id"))
    task_id: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSONB, default=list)
    default_option: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="open")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Budget(Base):
    __tablename__ = "budgets"

    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id"), primary_key=True)
    tokens_used: Mapped[int] = mapped_column(BigInteger, default=0)
    runs_used: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GithubToken(Base):
    __tablename__ = "github_tokens"

    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    token_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    scopes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()
