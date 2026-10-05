"""Presence (broadcast, never stored), sittings, and the background tick."""

import time
from uuid import uuid4

import pytest

from mux.events import log
from mux.rooms.actor import LOCK_IDLE_S, SITTING_IDLE_S, FileLock, RoomActor


@pytest.fixture
def published():
    return []


@pytest.fixture
def publish(published):
    async def _publish(event):
        published.append(event)
    return _publish


async def new_room(session_factory, publish):
    owner = uuid4()
    return await RoomActor.create(owner, "r", publish, template={}, sessionmaker=session_factory), owner


def after_create(published):
    return [e.type for e in published[2:]]


async def stored_types(session_factory, room_id):
    async with session_factory() as s:
        return [e.type for e in await log.read_all(room_id, session=s)]


async def test_presence_is_broadcast_not_stored(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    await actor.connect(owner, "Ada")
    await actor.set_tab(owner, "code")
    await actor.set_typing(owner, True)
    assert after_create(published) == ["presence.join", "presence.tab", "presence.typing"]
    assert published[2].payload == {"user_id": str(owner), "name": "Ada", "tab": None, "typing": False}
    assert all(e.seq == 2 for e in published[2:])  # the last stored seq, so a client's ?since does not move
    assert await stored_types(session_factory, actor.room_id) == ["room.created", "checkpoint.created"]


async def test_second_tab_leaves_only_with_the_last_connection(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    await actor.connect(owner)
    await actor.connect(owner)
    await actor.disconnect(owner)
    assert after_create(published) == ["presence.join"]
    assert owner in actor.presence
    await actor.disconnect(owner)
    assert after_create(published) == ["presence.join", "presence.leave"]
    assert owner not in actor.presence


async def test_no_change_and_strangers_are_not_broadcast(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    await actor.connect(owner)
    await actor.set_tab(owner, "code")
    await actor.set_tab(owner, "code")
    await actor.set_typing(uuid4(), True)
    assert after_create(published) == ["presence.join", "presence.tab"]


async def test_disconnect_releases_the_users_locks(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    await actor.connect(owner)
    await actor.lock_file("a.ts", owner)
    await actor.disconnect(owner)
    assert after_create(published) == ["presence.join", "file.locked", "presence.leave", "file.unlocked"]
    assert actor.locks == {}


async def test_sitting_ends_once_everyone_is_gone_long_enough(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    ended = []

    async def hook(reason):
        ended.append(reason)

    actor.on_sitting_end = hook
    await actor.connect(owner)
    await actor.disconnect(owner)
    assert actor.empty_since is not None
    await actor.tick()  # not 30 minutes yet
    assert "sitting.ended" not in after_create(published)
    actor.empty_since = time.monotonic() - SITTING_IDLE_S - 1
    await actor.tick()
    await actor.tick()  # already ended: no second event
    assert after_create(published).count("sitting.ended") == 1
    assert published[-1].payload == {"reason": "idle"}
    assert ended == ["idle"]
    assert "sitting.ended" in await stored_types(session_factory, actor.room_id)


async def test_owner_ends_the_session_and_a_new_join_starts_another(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    await actor.connect(owner)
    assert await actor.end_session(owner)
    assert not await actor.end_session(owner)  # nothing left to end
    assert (published[-1].type, published[-1].payload) == ("sitting.ended", {"reason": "owner"})
    assert not actor.sitting_active
    await actor.connect(uuid4())
    assert actor.sitting_active


async def test_tick_expires_idle_locks(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    await actor.lock_file("a.ts", owner)
    actor.locks["a.ts"] = FileLock(owner, time.monotonic() - LOCK_IDLE_S - 1)
    await actor.tick()
    assert actor.locks == {}
    assert published[-1].type == "file.unlocked"


async def test_background_tick_starts_and_stops(session_factory, publish):
    actor, _ = await new_room(session_factory, publish)
    actor.start()
    actor.start()  # twice is harmless
    assert actor._ticker is not None
    assert not actor._ticker.done()
    await actor.stop()
    assert actor._ticker is None
