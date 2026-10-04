"""Tests for checkpoints and rewind."""
"""Tests for checkpoints and rewind.

Assumption (DB_TASK names no job for this file): it covers T7 `checkpoint.py` against Postgres and
T8 `rewind.py` against the shared scenario in `mux/packages/schema/fixtures/rewind_scenario.json`.
"""

import dataclasses
import json
from typing import Literal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from mux.checkpoints import checkpoint
from mux.checkpoints.checkpoint import CheckpointRow, LogRow, created_payload
from mux.checkpoints.rewind import (
    active_seqs,
    compute_active,
    head_state,
    nearest_snapshot,
    path_to_root,
    rewound_payload,
)
from tests.conftest import safe_test_database_url
from mux.db.session import make_engine
from mux.db.tables import Log, Room
from mux.events import log
from mux.events.models import CheckpointCreated, EventEnvelope, RoomRewound, is_exempt
from mux.files import manifest as mf
from mux.files import store
from mux.files.manifest import Entry, LiveFiles, Manifest

SCENARIO = json.loads(
    (Path(__file__).resolve().parents[2] / "packages/schema/fixtures/rewind_scenario.json").read_text()
)
ROOM = uuid4()
TS = datetime(2026, 10, 1, tzinfo=timezone.utc)


def cid(name: str) -> UUID:
    """Checkpoint id for a scenario name like "C2"."""
    return UUID(SCENARIO["checkpoints"][name])


def events_upto(seq: int) -> list[EventEnvelope]:
    """Scenario events with seq <= `seq`."""
    return [
        EventEnvelope(seq=e["seq"], room_id=ROOM, type=e["type"], actor="coder", ts=TS, payload=e["payload"])
        for e in SCENARIO["events"]
        if e["seq"] <= seq
    ]


def rows_from(events: list[EventEnvelope]) -> dict[UUID, CheckpointRow]:
    """Checkpoint rows as the `checkpoint.created` payloads describe them."""
    rows = {}
    for e in events:
        if e.type == "checkpoint.created":
            p = CheckpointCreated.model_validate(e.payload)
            rows[p.checkpoint_id] = CheckpointRow(
                id=p.checkpoint_id, room_id=ROOM, seq=e.seq, start_seq=p.start_seq, parent_id=p.parent_id,
                manifest_id=p.manifest_id, sandbox_snapshot_uuid=p.sandbox_snapshot_uuid,
            )
    return rows


ALL = rows_from(events_upto(10**6))


def active_at(seq: int, head: str) -> set[int]:
    events = events_upto(seq)
    return compute_active(events, rows_from(events), cid(head))


async def load_scenario_manifest(manifest_id: UUID) -> Manifest:
    entries = SCENARIO["manifests"][str(manifest_id)]
    return {p: Entry(v["hash"], v["version"]) for p, v in entries.items()}


# ---- rewind.py: pure ----


def test_path_to_root_follows_parents() -> None:
    assert [c.id for c in path_to_root(cid("C5"), ALL)] == [cid("C5"), cid("C2"), cid("C1"), cid("C0")]


@pytest.mark.parametrize("step", SCENARIO["steps"], ids=lambda s: f"seq{s['after_seq']}-{s['head']}")
def test_matches_shared_cases(step: dict) -> None:
    assert active_at(step["after_seq"], step["head"]) == set(step["active"])


def test_active_after_c2_then_c5() -> None:
    active = active_at(17, "C5")
    assert {15, 16, 17} <= active  # C5's work and the WIP after it
    assert not {9, 12} & active  # C3/C4 work, dead since the rewind to C2


def test_click_c4_greys_c5_and_wip() -> None:
    active = active_at(18, "C4")
    assert not {15, 17} & active
    assert {9, 12} <= active


def test_exempt_never_greyed() -> None:
    for step in SCENARIO["steps"]:
        exempt = {e.seq for e in events_upto(step["after_seq"]) if is_exempt(e.type)}
        assert exempt <= active_at(step["after_seq"], step["head"])
    assert 10 in active_at(14, "C2")  # message.posted inside a greyed task


def test_rewind_to_head_drops_wip() -> None:
    assert 19 in active_at(19, "C4")
    assert 19 not in active_at(20, "C4")


def test_no_head_everything_active() -> None:
    events = events_upto(1)
    assert compute_active(events, {}, None) == {1}


async def test_versions_up_after_rewind() -> None:
    for e in events_upto(10**6):
        if e.type != "room.rewound":
            continue
        expected = RoomRewound.model_validate(e.payload)
        live = await LiveFiles.replay(events_upto(e.seq - 1), load_scenario_manifest)
        target = await load_scenario_manifest(ALL[expected.checkpoint_id].manifest_id)
        got = rewound_payload(live, expected.checkpoint_id, target)
        assert got == expected, f"seq {e.seq}"
        assert all(v > live.high_water.get(p, 0) for p, v in got.versions.items())


def test_log_nearest_on_path() -> None:
    def log_on(name: str, kind: Literal["task", "day"], hours: int) -> LogRow:
        return LogRow(id=uuid4(), kind=kind, body=f"{name} {kind}", pins=[], checkpoint_id=cid(name),
                      created_at=TS + timedelta(hours=hours))

    c1, c3_task, c3_day, c5 = log_on("C1", "task", 1), log_on("C3", "task", 3), log_on("C3", "day", 4), log_on("C5", "task", 9)
    logs = [c1, c3_task, c3_day, c5]
    assert head_state(cid("C2"), ALL, logs).log == c1  # C2 has no log; C5's is newer but off the path
    assert head_state(cid("C3"), ALL, logs).log == c3_day  # latest log on the nearest checkpoint
    assert head_state(cid("C4"), ALL, logs).log == c3_day
    assert head_state(cid("C0"), ALL, logs).log is None
    hs = head_state(cid("C4"), ALL, logs)
    assert (hs.checkpoint_id, hs.manifest_id, hs.plan) == (cid("C4"), ALL[cid("C4")].manifest_id, [])


def test_nearest_snapshot_skips_nulls() -> None:
    assert nearest_snapshot(cid("C3"), ALL) == "snap-2"
    assert nearest_snapshot(cid("C4"), ALL) == "snap-4"
    assert nearest_snapshot(cid("C0"), ALL) is None


# ---- checkpoint.py: Postgres ----


def ev(room_id: UUID, seq: int, type: str = "checkpoint.created", payload: dict | None = None) -> EventEnvelope:
    return EventEnvelope(seq=seq, room_id=room_id, type=type, actor="coder", ts=TS, payload=payload or {})


async def make_c0(session: AsyncSession, room_id: UUID) -> CheckpointRow:
    return await checkpoint.create_root(
        room_id, {"src/App.tsx": b"one\r\n", "logo.png": b"\x89PNG\r\n"}, ev(room_id, 2), session=session
    )


async def next_cp(session: AsyncSession, parent: CheckpointRow, seq: int, snap: str | None = None) -> CheckpointRow:
    mid = await mf.save(parent.room_id, {"src/App.tsx": Entry(store.hash_bytes(b"two\n"), 2)}, session=session)
    return CheckpointRow(id=uuid4(), room_id=parent.room_id, seq=seq, start_seq=parent.seq, parent_id=parent.id,
                         manifest_id=mid, sandbox_snapshot_uuid=snap, plan=[{"title": "Add nav"}])


def task_log(cp: CheckpointRow) -> LogRow:
    return LogRow(id=uuid4(), kind="task", body="did the thing", pins=["keep tailwind"], checkpoint_id=cp.id)


async def head_of(session: AsyncSession, room_id: UUID) -> UUID | None:
    return await session.scalar(select(Room.head_checkpoint_id).where(Room.id == room_id))


async def test_root_no_parent_seq0_null_uuid(db_session: AsyncSession, room: UUID) -> None:
    c0 = await make_c0(db_session, room)
    loaded = await checkpoint.load(c0.id, session=db_session)
    assert (loaded.parent_id, loaded.start_seq, loaded.seq, loaded.sandbox_snapshot_uuid) == (None, 0, 2, None)
    m = await mf.load(c0.manifest_id, session=db_session)
    assert m["src/App.tsx"] == Entry(store.hash_bytes(b"one\n"), 1)  # LF-normalised, version 1
    assert m["logo.png"].version == 1
    [event] = await log.read_all(room, session=db_session)
    assert (event.seq, event.payload) == (2, created_payload(c0))


async def test_roundtrip(db_session: AsyncSession, room: UUID) -> None:
    c0 = await make_c0(db_session, room)
    c1 = await next_cp(db_session, c0, seq=4, snap="snap-1")
    tl = task_log(c1)
    saved = await checkpoint.save(c1, tl, ev(room, 4, payload=created_payload(c1)), session=db_session)
    loaded = await checkpoint.load(c1.id, session=db_session)
    assert dataclasses.replace(loaded, created_at=None) == c1
    assert loaded.created_at is not None and saved.created_at is not None
    assert set(await checkpoint.load_all(room, session=db_session)) == {c0.id, c1.id}
    [got] = await checkpoint.load_logs(room, session=db_session)
    assert dataclasses.replace(got, created_at=None) == tl


async def test_save_moves_head(db_session: AsyncSession, room: UUID) -> None:
    c0 = await make_c0(db_session, room)
    assert await head_of(db_session, room) == c0.id
    c1 = await next_cp(db_session, c0, seq=4)
    await checkpoint.save(c1, None, ev(room, 4), session=db_session)
    assert await head_of(db_session, room) == c1.id


async def test_checkpoint_log_and_event_commit_together(db_session: AsyncSession, room: UUID) -> None:
    c0 = await make_c0(db_session, room)
    c1 = await next_cp(db_session, c0, seq=4)
    await checkpoint.save(c1, task_log(c1), ev(room, 4), session=db_session)
    await db_session.commit()

    engine = make_engine(safe_test_database_url(), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as other:
            assert (await checkpoint.load(c1.id, session=other)).id == c1.id
            assert [lg.checkpoint_id for lg in await checkpoint.load_logs(room, session=other)] == [c1.id]
            assert [e.seq for e in await log.read_all(room, session=other)] == [2, 4]
            assert await head_of(other, room) == c1.id
    finally:
        await engine.dispose()


async def test_failure_rolls_back_all_three(db_session: AsyncSession, room: UUID) -> None:
    c0 = await make_c0(db_session, room)
    await log.append(room, [ev(room, 4, type="task.started")], session=db_session)
    c1 = await next_cp(db_session, c0, seq=4)
    with pytest.raises(IntegrityError):  # the event insert fails after the checkpoint and log rows
        await checkpoint.save(c1, task_log(c1), ev(room, 4), session=db_session)
    with pytest.raises(KeyError):
        await checkpoint.load(c1.id, session=db_session)
    assert await checkpoint.load_logs(room, session=db_session) == []
    assert await head_of(db_session, room) == c0.id


@pytest.mark.parametrize("bad", ["type", "seq", "payload", "log"])
async def test_rejects_mismatched_event(db_session: AsyncSession, room: UUID, bad: str) -> None:
    c0 = await make_c0(db_session, room)
    c1 = await next_cp(db_session, c0, seq=4)
    event, tl = ev(room, 4), task_log(c1)
    if bad == "type":
        event = ev(room, 4, type="task.finished")
    elif bad == "seq":
        event = ev(room, 5)
    elif bad == "payload":
        event = ev(room, 4, payload=created_payload(c0))
    else:
        tl = dataclasses.replace(tl, checkpoint_id=c0.id)
    with pytest.raises(ValueError):
        await checkpoint.save(c1, tl, event, session=db_session)
    with pytest.raises(KeyError):
        await checkpoint.load(c1.id, session=db_session)


async def test_active_seqs_from_db(db_session: AsyncSession, room: UUID) -> None:
    await log.append(room, [ev(room, 1, type="room.created")], session=db_session)
    c0 = await make_c0(db_session, room)
    await log.append(room, [ev(room, 3, type="task.started")], session=db_session)
    c1 = await next_cp(db_session, c0, seq=4)
    await checkpoint.save(c1, None, ev(room, 4), session=db_session)
    assert await active_seqs(room, session=db_session) == {1, 2, 3, 4}

    # The actor's rewind to C0: set the head and emit room.rewound (R2).
    await db_session.execute(update(Room).where(Room.id == room).values(head_checkpoint_id=c0.id))
    rewound = RoomRewound(checkpoint_id=c0.id, versions={}).model_dump(mode="json")
    await log.append(room, [ev(room, 5, type="room.rewound", payload=rewound)], session=db_session)
    assert await active_seqs(room, session=db_session) == {1, 2, 4, 5}


async def test_logs_in_one_transaction_keep_their_order(db_session: AsyncSession, room: UUID) -> None:
    c0 = await make_c0(db_session, room)
    for kind in ("task", "day"):  # same transaction: now() would give both the same created_at
        db_session.add(Log(id=uuid4(), room_id=room, kind=kind, body=kind, pins=[], checkpoint_id=c0.id))
        await db_session.flush()
    logs = await checkpoint.load_logs(room, session=db_session)
    assert [lg.kind for lg in logs] == ["task", "day"]
    assert logs[0].created_at is not None and logs[1].created_at is not None
    assert logs[0].created_at < logs[1].created_at
    assert head_state(c0.id, {c0.id: c0}, logs).log == logs[1]
