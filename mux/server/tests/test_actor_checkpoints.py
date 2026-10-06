"""Checkpoints from the actor: C0 from the template, save_checkpoint, and reopening."""

from uuid import UUID, uuid4

import pytest

from mux.checkpoints import checkpoint
from mux.events.models import PlanItem
from mux.files import manifest
from mux.files.template import load_template
from mux.rooms import records
from mux.rooms.actor import RoomActor

TEMPLATE = {"package.json": b"{}\n", "src/App.tsx": b"export {}\n"}


@pytest.fixture
def published():
    return []


@pytest.fixture
def publish(published):
    async def _publish(event):
        published.append(event)
    return _publish


async def new_room(session_factory, publish, template=TEMPLATE):
    owner = uuid4()
    actor = await RoomActor.create(owner, "r", publish, template=template, sessionmaker=session_factory)
    return actor, owner


async def test_create_saves_c0_from_the_template(session_factory, publish, published):
    actor, _ = await new_room(session_factory, publish)
    assert [e.type for e in published] == ["room.created", "checkpoint.created"]
    c0 = published[1]
    assert c0.payload["parent_id"] is None
    assert c0.payload["start_seq"] == 0
    assert actor.record.head_checkpoint_id == UUID(c0.payload["checkpoint_id"])
    assert actor.head_seq == c0.seq == 2
    assert await actor.read_file("src/App.tsx") == (b"export {}\n", 1)
    async with session_factory() as s:
        stored = await records.load(actor.room_id, session=s)
    assert stored is not None
    assert stored.head_checkpoint_id == actor.record.head_checkpoint_id


async def test_empty_template(session_factory, publish):
    actor, _ = await new_room(session_factory, publish, template={})
    assert actor.files.manifest == {}
    assert actor.record.head_checkpoint_id is not None


async def test_save_checkpoint_after_an_edit(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    c0_id = actor.record.head_checkpoint_id
    await actor.lock_file("src/App.tsx", owner)
    await actor.save_file("src/App.tsx", b"export const x = 1\n", 1, owner)
    await actor.draft_plan([PlanItem(id="t1", title="Login")], "coordinator")
    cp = await actor.save_checkpoint("agent", snapshot_uuid="snap-1", log_body="Built the login page")

    assert (cp.parent_id, cp.start_seq, cp.sandbox_snapshot_uuid) == (c0_id, 2, "snap-1")
    assert actor.record.head_checkpoint_id == cp.id
    assert actor.head_seq == cp.seq
    assert (published[-2].type, published[-2].seq) == ("checkpoint.created", cp.seq)
    assert published[-2].payload["checkpoint_id"] == str(cp.id)
    assert (published[-1].type, published[-1].payload["checkpoint_id"]) == ("log.task_written", str(cp.id))
    assert cp.plan == [actor.plan[0].model_dump(mode="json")]
    async with session_factory() as s:
        saved = await manifest.load(cp.manifest_id, session=s)
        logs = await checkpoint.load_logs(actor.room_id, session=s)
    assert saved["src/App.tsx"].version == 2
    assert [(lg.kind, lg.body, lg.checkpoint_id) for lg in logs] == [("task", "Built the login page", cp.id)]


async def test_reopen_keeps_checkpoints_and_head(session_factory, publish):
    actor, _ = await new_room(session_factory, publish)
    cp = await actor.save_checkpoint("agent")
    reopened = await RoomActor.open(actor.room_id, publish, sessionmaker=session_factory)
    assert reopened is not None
    assert reopened.checkpoints.keys() == actor.checkpoints.keys()
    assert reopened.head_seq == actor.head_seq
    assert reopened.record.head_checkpoint_id == cp.id
    child = await reopened.save_checkpoint("agent")
    assert (child.parent_id, child.start_seq) == (cp.id, cp.seq)


def test_load_template_skips_build_folders(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("a")
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "i.js").write_text("x")
    assert load_template(tmp_path) == {"src/a.ts": b"a"}


def test_real_template_loads():
    template = load_template()
    assert {"package.json", "package-lock.json", "src/App.tsx", "src/server/app.ts", "CONVENTIONS.md"} <= set(template)
