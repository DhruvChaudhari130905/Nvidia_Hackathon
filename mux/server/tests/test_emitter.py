
"""Emitter: contiguous seqs, broadcast after commit, rollback, failed broadcasts, concurrent emits."""

import asyncio
from uuid import uuid4

import pytest

from mux.events import log
from mux.events.models import FileChanged
from mux.rooms import records
from mux.rooms.emitter import Emitter


@pytest.fixture
async def stored_room(session_factory):
    """A committed room row (events have a foreign key to it)."""
    async with session_factory() as s, s.begin():
        room = await records.create(uuid4(), "r", session=s)
    return room.id


async def make(session_factory, room_id, published):
    async def publish(event):
        published.append(event)
    return await Emitter.resume(room_id, publish, sessionmaker=session_factory)


async def test_contiguous_seqs_published_after_commit(session_factory, stored_room):
    published = []
    em = await make(session_factory, stored_room, published)
    async with em.transaction() as tx:
        await tx.emit("plan.drafted", {"items": []}, "u1")
        await tx.emit("plan.approved", {}, "u1")
        assert published == []  # nothing goes out before the commit
    assert [e.seq for e in published] == [1, 2]
    assert em.seq == 2
    async with session_factory() as s:
        stored = await log.read_all(stored_room, session=s)
    assert [(e.seq, e.type, e.payload) for e in stored] == [(1, "plan.drafted", {"items": []}), (2, "plan.approved", {})]


async def test_resume_continues_after_stored_seq(session_factory, stored_room):
    first = await make(session_factory, stored_room, [])
    await first.emit("plan.approved", {}, "u1")
    second = await make(session_factory, stored_room, [])
    assert second.seq == 1
    assert (await second.emit("plan.approved", {}, "u1")).seq == 2


async def test_exception_stores_and_publishes_nothing(session_factory, stored_room):
    published = []
    em = await make(session_factory, stored_room, published)
    with pytest.raises(RuntimeError):
        async with em.transaction() as tx:
            await tx.emit("plan.approved", {}, "u1")
            raise RuntimeError("boom")
    assert published == []
    assert em.seq == 0
    assert (await em.emit("plan.approved", {}, "u1")).seq == 1  # the rolled-back seq is used again


async def test_failed_publish_keeps_the_event(session_factory, stored_room):
    calls = []

    async def publish(event):
        calls.append(event.seq)
        if event.seq == 1:
            raise ConnectionError("socket gone")

    em = await Emitter.resume(stored_room, publish, sessionmaker=session_factory)
    async with em.transaction() as tx:
        await tx.emit("plan.approved", {}, "u1")
        await tx.emit("plan.approved", {}, "u1")
    assert calls == [1, 2]  # the second event still went out
    assert em.seq == 2


async def test_concurrent_emits_get_unique_ordered_seqs(session_factory, stored_room):
    published = []
    em = await make(session_factory, stored_room, published)
    await asyncio.gather(*(em.emit("plan.approved", {"n": i}, "u1") for i in range(10)))
    assert [e.seq for e in published] == list(range(1, 11))


async def test_payload_model_stored_as_json(session_factory, stored_room):
    em = await make(session_factory, stored_room, [])
    changed = FileChanged(path="a.ts", hash="h1", version=1, base_version=None, deleted=False,
                          actor="u1", diff_summary="+1 line")
    event = await em.emit("file.changed", changed, "u1")
    assert event.payload["path"] == "a.ts"
    assert event.payload["base_version"] is None
