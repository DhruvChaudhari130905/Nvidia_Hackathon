"""Rewind: which events are active for a head, the restored head state, and the `room.rewound` payload.

Events are never edited (Q40). The actor moves `rooms.head_checkpoint_id` and appends `room.rewound`; the
active set is then computed from the checkpoint tree:

- each checkpoint on the path from the head to the root owns the events in `(start_seq, seq]` (R4);
- events after the latest head change (`checkpoint.created` or `room.rewound`) are work in progress on the head;
- exempt (room-level) events are never greyed (Q41).

Stopping the coder and re-classifying the inbox belong to the room actor.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mux.checkpoints import checkpoint
from mux.checkpoints.checkpoint import CheckpointRow, LogRow
from mux.db.tables import Room
from mux.events import log
from mux.events.log import scoped
from mux.events.models import EventEnvelope, RoomId, RoomRewound, is_exempt
from mux.files.manifest import LiveFiles, Manifest, restore_versions

HEAD_CHANGES = frozenset({"checkpoint.created", "room.rewound"})


@dataclass(frozen=True)
class HeadState:
    """What a rewind makes current: the manifest, the plan, and the nearest log on the path (R6)."""

    checkpoint_id: UUID
    manifest_id: UUID
    plan: list[dict]
    log: LogRow | None


def path_to_root(head_id: UUID, checkpoints: Mapping[UUID, CheckpointRow]) -> list[CheckpointRow]:
    """`head_id` and its ancestors, head first. Raises KeyError for an unknown id."""
    path: list[CheckpointRow] = []
    cur: UUID | None = head_id
    while cur is not None:
        cp = checkpoints[cur]
        path.append(cp)
        cur = cp.parent_id
        if len(path) > len(checkpoints):
            raise ValueError(f"checkpoint parent cycle at {head_id}")
    return path


def compute_active(
    events: Sequence[EventEnvelope], checkpoints: Mapping[UUID, CheckpointRow], head_id: UUID | None
) -> set[int]:
    """Seqs of the events that are not greyed out with `head_id` as head. No head: everything is active."""
    if head_id is None:
        return {e.seq for e in events}
    spans = [(cp.start_seq, cp.seq) for cp in path_to_root(head_id, checkpoints)]
    last_change = max((e.seq for e in events if e.type in HEAD_CHANGES), default=0)
    return {
        e.seq
        for e in events
        if is_exempt(e.type) or e.seq > last_change or any(lo < e.seq <= hi for lo, hi in spans)
    }


async def active_seqs(room_id: RoomId, *, session: AsyncSession | None = None) -> set[int]:
    """`compute_active` for the room as stored: its events, checkpoints and current head."""
    async with scoped(session) as s:
        head = await s.scalar(select(Room.head_checkpoint_id).where(Room.id == room_id))
        events = await log.read_all(room_id, session=s)
        checkpoints = await checkpoint.load_all(room_id, session=s)
    return compute_active(events, checkpoints, head)


def nearest_snapshot(head_id: UUID, checkpoints: Mapping[UUID, CheckpointRow]) -> str | None:
    """The sandbox snapshot of the head or its nearest ancestor that has one (a failed build leaves it null)."""
    return next((cp.sandbox_snapshot_uuid for cp in path_to_root(head_id, checkpoints) if cp.sandbox_snapshot_uuid), None)


def head_state(head_id: UUID, checkpoints: Mapping[UUID, CheckpointRow], logs: Sequence[LogRow]) -> HeadState:
    """The head's manifest and plan, and the newest log of the nearest checkpoint on the path that has one.

    Logs of dead branches are never picked, so the agent does not remember undone work (§11).
    """
    path = path_to_root(head_id, checkpoints)
    by_cp: dict[UUID, list[LogRow]] = {}
    for lg in logs:
        by_cp.setdefault(lg.checkpoint_id, []).append(lg)
    found = next((by_cp[cp.id] for cp in path if cp.id in by_cp), [])
    # created_at is None only for rows not yet saved; those sort before saved ones instead of failing.
    latest = max(found, key=lambda lg: (lg.created_at is not None, lg.created_at or 0), default=None)
    head = path[0]
    return HeadState(checkpoint_id=head.id, manifest_id=head.manifest_id, plan=list(head.plan), log=latest)


def rewound_payload(live: LiveFiles, checkpoint_id: UUID, target: Manifest) -> RoomRewound:
    """The `room.rewound` payload: every path whose content changes gets a version above its high-water mark (DB4)."""
    return RoomRewound(checkpoint_id=checkpoint_id, versions=restore_versions(live.manifest, target, live.high_water))
