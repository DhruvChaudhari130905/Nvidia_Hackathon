
"""RoomActor core: create and open, members, joining by link, sharing, messages."""

from uuid import uuid4

import pytest

from mux.events.models import PlanItem
from mux.events import log
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


async def new_room(session_factory, publish, owner=None, **kwargs):
    return await RoomActor.create(owner or uuid4(), "Todo app", publish, template={}, sessionmaker=session_factory, **kwargs)


async def stored(session_factory, room_id):
    async with session_factory() as s:
        return await records.load(room_id, session=s), await log.read_all(room_id, session=s)


async def test_create_writes_room_owner_and_event(session_factory, publish, published):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, description="d", domain_role="pm")
    assert actor.role_of(owner) == "owner"
    assert [(e.seq, e.type) for e in published] == [(1, "room.created"), (2, "checkpoint.created")]
    assert published[0].payload == {"owner_id": str(owner), "title": "Todo app", "description": "d"}
    record, events = await stored(session_factory, actor.room_id)
    assert record == actor.record
    assert len(events) == 2


async def test_open_unknown_room(session_factory, publish):
    assert await RoomActor.open(uuid4(), publish, sessionmaker=session_factory) is None


async def test_open_resumes_record_and_seq(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner)
    await actor.post_message(owner, "hello")
    reopened = await RoomActor.open(actor.room_id, publish, sessionmaker=session_factory)
    assert reopened is not None
    assert reopened.record == actor.record
    assert reopened.emitter.seq == 3


async def test_set_member_joins_then_changes_role(session_factory, publish, published):
    owner, user = uuid4(), uuid4()
    actor = await new_room(session_factory, publish, owner)
    await actor.set_member(user, "viewer", by=owner, domain_role="design")
    await actor.set_member(user, "editor", by=owner)
    assert [e.type for e in published] == ["room.created", "checkpoint.created", "member.joined", "member.role_changed"]
    assert actor.record.members[user] == records.Member("editor", "design")
    record, _ = await stored(session_factory, actor.room_id)
    assert record is not None
    assert record.members[user] == records.Member("editor", "design")


async def test_failed_change_stores_nothing_and_keeps_state(session_factory, publish, published):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner)
    before = actor.record
    with pytest.raises(ValueError):
        await actor.set_member(owner, "editor", by=owner)  # the owner's permission cannot change
    assert actor.record == before
    assert [e.type for e in published] == ["room.created", "checkpoint.created"]
    assert actor.emitter.seq == 2


async def test_join_private_room_raises(session_factory, publish):
    actor = await new_room(session_factory, publish)
    with pytest.raises(PermissionError):
        await actor.join(uuid4())


async def test_join_open_room_gets_link_permission_once(session_factory, publish, published):
    owner, stranger = uuid4(), uuid4()
    actor = await new_room(session_factory, publish, owner)
    await actor.set_sharing("anyone", "viewer", by=owner)
    assert await actor.join(stranger, "eng") == "viewer"
    assert await actor.join(stranger) == "viewer"  # already a member: no second event
    assert [e.type for e in published] == ["room.created", "checkpoint.created", "sharing.changed", "member.joined"]
    assert published[-1].actor == str(stranger)


async def test_restricted_sharing_clears_link_permission(session_factory, publish, published):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner)
    await actor.set_sharing("restricted", "editor", by=owner)
    assert published[-1].payload == {"link_access": "restricted", "link_permission": None}
    assert actor.record.link_permission is None


async def test_post_message(session_factory, publish, published):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner)
    message = await actor.post_message(owner, "add dark mode", to="team")
    assert published[-1].type == "message.posted"
    assert published[-1].payload == {"id": str(message.id), "user_id": str(owner), "text": "add dark mode", "to": "team"}


async def test_plan_changes_are_stored_and_replayed_on_open(session_factory, publish, published):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner)
    await actor.draft_plan([PlanItem(id="t1", title="Login"), PlanItem(id="t2", title="Todo list")], "coordinator")
    await actor.approve_plan(str(owner))
    await actor.start_task("t1")
    await actor.update_plan_item("t2", {"notes": "use SQLite"}, str(owner))
    assert [e.type for e in published[2:]] == ["plan.drafted", "plan.approved", "task.started", "plan.item_updated"]
    assert [(i.id, i.status) for i in actor.plan] == [("t1", "doing"), ("t2", "todo")]

    reopened = await RoomActor.open(actor.room_id, publish, sessionmaker=session_factory)
    assert reopened is not None
    assert reopened.plan == actor.plan
    assert reopened.emitter.seq == actor.emitter.seq == 6


async def test_broken_plan_rule_writes_nothing(session_factory, publish, published):
    actor = await new_room(session_factory, publish)
    await actor.draft_plan([PlanItem(id="t1", title="Login")], "coordinator")
    before = actor.plan
    with pytest.raises(ValueError):
        await actor.start_task("t1")  # still a draft
    assert actor.plan == before
    assert [e.type for e in published] == ["room.created", "checkpoint.created", "plan.drafted"]
