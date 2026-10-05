
"""Rewind: files, plan, head and log jump to a checkpoint; replay on open gives the same state."""

from uuid import uuid4

import pytest

from mux.events.models import PlanItem
from mux.rooms import records
from mux.rooms.actor import RoomActor


@pytest.fixture
def published():
    return []


@pytest.fixture
def publish(published):
    async def _publish(event):
        published.append(event)
    return _publish


async def worked_room(session_factory, publish):
    """C0 (a.ts v1) -> edit a.ts to v2, draft t1 -> checkpoint cp1 -> edit a.ts to v3, add b.ts, approve."""
    owner = uuid4()
    actor = await RoomActor.create(owner, "r", publish, template={"a.ts": b"one\n"}, sessionmaker=session_factory)
    await actor.lock_file("a.ts", owner)
    await actor.save_file("a.ts", b"two\n", 1, owner)
    await actor.draft_plan([PlanItem(id="t1", title="Login")], "coordinator")
    cp1 = await actor.save_checkpoint("agent", log_body="log1")
    await actor.save_file("a.ts", b"three\n", 2, owner)
    await actor.lock_file("b.ts", owner)
    await actor.save_file("b.ts", b"new\n", None, owner)
    await actor.approve_plan(str(owner))
    return actor, owner, cp1


async def test_rewind_restores_files_plan_and_head(session_factory, publish, published):
    actor, owner, cp1 = await worked_room(session_factory, publish)
    state = await actor.rewind_to(cp1.id, str(owner))

    event = published[-1]
    assert event.type == "room.rewound"
    assert event.payload == {"checkpoint_id": str(cp1.id), "versions": {"a.ts": 4}}  # above every version a.ts had
    assert await actor.read_file("a.ts") == (b"two\n", 4)
    with pytest.raises(KeyError):
        await actor.read_file("b.ts")  # not in cp1
    assert [(i.id, i.status) for i in actor.plan] == [("t1", "draft")]
    assert actor.record.head_checkpoint_id == cp1.id
    assert actor.head_seq == event.seq
    assert state.log is not None
    assert state.log.body == "log1"
    async with session_factory() as s:
        stored = await records.load(actor.room_id, session=s)
    assert stored is not None
    assert stored.head_checkpoint_id == cp1.id


async def test_stale_base_version_after_rewind(session_factory, publish):
    actor, owner, cp1 = await worked_room(session_factory, publish)
    await actor.rewind_to(cp1.id, str(owner))
    result = await actor.save_file("a.ts", b"mine\n", 3, owner)  # v3 is the undone version
    assert (result.ok, result.version) == (False, 4)


async def test_checkpoint_after_rewind_branches_from_the_target(session_factory, publish, published):
    actor, owner, _ = await worked_room(session_factory, publish)
    c0_id = next(cp.id for cp in actor.checkpoints.values() if cp.parent_id is None)
    await actor.rewind_to(c0_id, str(owner))
    rewound_seq = published[-1].seq
    child = await actor.save_checkpoint("agent")
    assert (child.parent_id, child.start_seq) == (c0_id, rewound_seq)


async def test_rewind_forward_again(session_factory, publish):
    actor, owner, cp1 = await worked_room(session_factory, publish)
    c0_id = cp1.parent_id
    assert c0_id is not None
    await actor.rewind_to(c0_id, str(owner))
    assert (await actor.read_file("a.ts"))[0] == b"one\n"
    assert actor.plan == ()
    await actor.rewind_to(cp1.id, str(owner))
    assert (await actor.read_file("a.ts"))[0] == b"two\n"
    assert [i.id for i in actor.plan] == ["t1"]


async def test_reopen_after_rewind_gives_the_same_state(session_factory, publish):
    actor, owner, cp1 = await worked_room(session_factory, publish)
    await actor.rewind_to(cp1.id, str(owner))
    await actor.add_plan_item(PlanItem(id="t2", title="Todo list", status="todo"), str(owner))
    reopened = await RoomActor.open(actor.room_id, publish, sessionmaker=session_factory)
    assert reopened is not None
    assert reopened.plan == actor.plan
    assert await reopened.read_file("a.ts") == await actor.read_file("a.ts")
    assert reopened.files.manifest == actor.files.manifest
    assert reopened.head_seq == actor.head_seq
    assert reopened.record.head_checkpoint_id == cp1.id


async def test_unknown_checkpoint_changes_nothing(session_factory, publish, published):
    actor, owner, _ = await worked_room(session_factory, publish)
    count = len(published)
    with pytest.raises(KeyError):
        await actor.rewind_to(uuid4(), str(owner))
    assert len(published) == count