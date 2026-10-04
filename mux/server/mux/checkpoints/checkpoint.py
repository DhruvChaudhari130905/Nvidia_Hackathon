"""Save and load checkpoints and their logs. A save writes the checkpoint, its task log, its `checkpoint.created`
event and the room head in one transaction (R4, R6). C0 is built from the template files (DB6)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mux.db.tables import Checkpoint, Log, Room
from mux.events import log
from mux.events.log import scoped
from mux.events.models import CheckpointCreated, EventEnvelope, RoomId
from mux.files import manifest, store
from mux.files.manifest import Entry


@dataclass(frozen=True)
class CheckpointRow:
    """A checkpoint. `seq` is its own `checkpoint.created` seq; `start_seq` the head change before it (R4)."""

    id: UUID
    room_id: RoomId
    seq: int
    start_seq: int
    parent_id: UUID | None
    manifest_id: UUID
    sandbox_snapshot_uuid: str | None
    plan: list[dict] = field(default_factory=list)
    created_at: datetime | None = None


@dataclass(frozen=True)
class LogRow:
    """A task or day log, pointing at its checkpoint (R6)."""

    id: UUID
    kind: Literal["task", "day"]
    body: str
    pins: list
    checkpoint_id: UUID
    created_at: datetime | None = None


def created_payload(cp: CheckpointRow) -> dict:
    """The `checkpoint.created` payload for `cp`, as stored and broadcast."""
    return CheckpointCreated(
        checkpoint_id=cp.id, parent_id=cp.parent_id, start_seq=cp.start_seq,
        manifest_id=cp.manifest_id, sandbox_snapshot_uuid=cp.sandbox_snapshot_uuid,
    ).model_dump(mode="json")


def _to_row(c: Checkpoint) -> CheckpointRow:
    return CheckpointRow(id=c.id, room_id=c.room_id, seq=c.seq, start_seq=c.start_seq, parent_id=c.parent_id,
                         manifest_id=c.manifest_id, sandbox_snapshot_uuid=c.sandbox_snapshot_uuid,
                         plan=list(c.plan), created_at=c.created_at)


def _to_log(lg: Log) -> LogRow:
    return LogRow(id=lg.id, kind=cast(Literal["task", "day"], lg.kind), body=lg.body, pins=list(lg.pins), checkpoint_id=lg.checkpoint_id,
                  created_at=lg.created_at)


def _check(cp: CheckpointRow, task_log: LogRow | None, event: EventEnvelope) -> EventEnvelope:
    """Validate the event and log against `cp`; return the event with the derived payload."""
    payload = created_payload(cp)
    if event.type != "checkpoint.created" or event.seq != cp.seq or event.room_id != cp.room_id:
        raise ValueError("event must be the checkpoint's own checkpoint.created (same type, seq and room)")
    if event.payload and event.payload != payload:
        raise ValueError("event payload does not describe this checkpoint")
    if task_log is not None and task_log.checkpoint_id != cp.id:
        raise ValueError("task log points at another checkpoint")
    return event.model_copy(update={"payload": payload})


async def save(
    cp: CheckpointRow, task_log: LogRow | None, event: EventEnvelope, *, session: AsyncSession
) -> CheckpointRow:
    """Write checkpoint, task log, event and room head atomically (a savepoint; the caller commits).

    `event.payload` may be empty: it is filled from `cp`. Raises ValueError on a mismatched event or log.
    """
    event = _check(cp, task_log, event)
    async with session.begin_nested():
        row = Checkpoint(id=cp.id, room_id=cp.room_id, seq=cp.seq, start_seq=cp.start_seq, parent_id=cp.parent_id,
                         manifest_id=cp.manifest_id, sandbox_snapshot_uuid=cp.sandbox_snapshot_uuid, plan=cp.plan)
        session.add(row)
        await session.flush()  # checkpoint first: logs.checkpoint_id references it (R6)
        if task_log is not None:
            session.add(Log(id=task_log.id, room_id=cp.room_id, kind=task_log.kind, body=task_log.body,
                            pins=task_log.pins, checkpoint_id=cp.id))
            await session.flush()
        await log.append(cp.room_id, [event], session=session)
        await session.execute(update(Room).where(Room.id == cp.room_id).values(head_checkpoint_id=cp.id))
    await session.refresh(row, ["created_at"])
    return _to_row(row)


async def create_root(
    room_id: RoomId, template_files: Mapping[str, bytes], event: EventEnvelope, *, session: AsyncSession
) -> CheckpointRow:
    """Create C0 from the template: blobs, a manifest at version 1, the checkpoint, its event and the head (DB6)."""
    async with session.begin_nested():
        m = {path: Entry(await store.put(data, session=session), 1) for path, data in template_files.items()}
        mid = await manifest.save(room_id, m, session=session)
        cp = CheckpointRow(id=uuid4(), room_id=room_id, seq=event.seq, start_seq=0, parent_id=None,
                           manifest_id=mid, sandbox_snapshot_uuid=None)
        return await save(cp, None, event, session=session)


async def load(id: UUID, *, session: AsyncSession | None = None) -> CheckpointRow:
    """Load one checkpoint; raises KeyError if absent."""
    async with scoped(session) as s:
        row = await s.scalar(select(Checkpoint).where(Checkpoint.id == id))
        if row is None:
            raise KeyError(id)
        return _to_row(row)


async def load_all(room_id: RoomId, *, session: AsyncSession | None = None) -> dict[UUID, CheckpointRow]:
    """Every checkpoint of the room, by id (dead branches included)."""
    async with scoped(session) as s:
        rows = await s.scalars(select(Checkpoint).where(Checkpoint.room_id == room_id).order_by(Checkpoint.seq))
        return {r.id: _to_row(r) for r in rows}


async def load_logs(room_id: RoomId, *, session: AsyncSession | None = None) -> list[LogRow]:
    """Every task and day log of the room, oldest first."""
    async with scoped(session) as s:
        rows = await s.scalars(select(Log).where(Log.room_id == room_id).order_by(Log.created_at))
        return [_to_log(r) for r in rows]
