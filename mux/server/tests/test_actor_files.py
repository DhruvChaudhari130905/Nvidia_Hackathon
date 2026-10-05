
"""Actor files: manual saves through RoomFiles, soft locks, and replay on open."""

import time
from uuid import uuid4

import pytest

from mux.files.room_files import InvalidPath
from mux.rooms.actor import LOCK_IDLE_S, FileLock, FileLockError, RoomActor


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


def types(published):
    return [e.type for e in published[2:]]  # without room.created and C0


async def test_locked_save_creates_version_and_event(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    await actor.lock_file("src/App.tsx", owner)
    result = await actor.save_file("src/App.tsx", b"export {}\n", None, owner)
    assert (result.ok, result.version, result.changed) == (True, 1, True)
    assert types(published) == ["file.locked", "file.changed"]
    assert published[-1].payload["version"] == 1
    assert published[-1].actor == str(owner)
    assert await actor.read_file("src/App.tsx") == (b"export {}\n", 1)
    assert actor.edit_notes == [f"{owner} edited src/App.tsx (new -> v1)"]


async def test_save_needs_the_lock(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    other = uuid4()
    with pytest.raises(FileLockError):
        await actor.save_file("a.ts", b"x", None, owner)  # nobody holds the lock
    await actor.lock_file("a.ts", owner)
    with pytest.raises(FileLockError):
        await actor.save_file("a.ts", b"x", None, other)  # someone else holds it
    assert types(published) == ["file.locked"]


async def test_stale_base_version_changes_nothing(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    await actor.lock_file("a.ts", owner)
    await actor.save_file("a.ts", b"one\n", None, owner)
    result = await actor.save_file("a.ts", b"two\n", 7, owner)
    assert (result.ok, result.version, result.changed) == (False, 1, False)
    assert types(published) == ["file.locked", "file.changed"]
    assert await actor.read_file("a.ts") == (b"one\n", 1)


async def test_lock_rules(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    other = uuid4()
    await actor.lock_file("a.ts", owner)
    await actor.lock_file("a.ts", owner)  # a refresh: no second event
    with pytest.raises(FileLockError):
        await actor.lock_file("a.ts", other)
    with pytest.raises(FileLockError):
        await actor.unlock_file("a.ts", other)
    assert await actor.unlock_file("a.ts", other, force=True)  # the owner's override
    assert not await actor.unlock_file("a.ts", owner)  # already free
    assert types(published) == ["file.locked", "file.unlocked"]
    assert published[-1].payload["user_id"] == str(owner)  # whose lock it was
    assert published[-1].actor == str(other)  # who released it


async def test_idle_lock_expires(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    other = uuid4()
    await actor.lock_file("a.ts", owner)
    actor.locks["a.ts"] = FileLock(owner, time.monotonic() - LOCK_IDLE_S - 1)
    await actor.lock_file("a.ts", other)
    assert types(published) == ["file.locked", "file.unlocked", "file.locked"]
    assert published[3].actor == "system"
    assert actor.locks["a.ts"].user_id == other


async def test_disconnect_releases_only_that_users_locks(session_factory, publish):
    actor, owner = await new_room(session_factory, publish)
    other = uuid4()
    await actor.lock_file("a.ts", owner)
    await actor.lock_file("b.ts", other)
    await actor.release_user_locks(owner)
    assert set(actor.locks) == {"b.ts"}


async def test_invalid_path_rejected(session_factory, publish):
    actor, owner = await new_room(session_factory, publish)
    with pytest.raises(InvalidPath):
        await actor.lock_file("../etc/passwd", owner)


async def test_reopen_replays_files_but_not_locks(session_factory, publish):
    actor, owner = await new_room(session_factory, publish)
    await actor.lock_file("a.ts", owner)
    await actor.save_file("a.ts", b"one\n", None, owner)
    await actor.save_file("a.ts", b"two\n", 1, owner)
    reopened = await RoomActor.open(actor.room_id, publish, sessionmaker=session_factory)
    assert reopened is not None
    assert await reopened.read_file("a.ts") == (b"two\n", 2)
    assert reopened.locks == {}
