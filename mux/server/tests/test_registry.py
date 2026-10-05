
"""RoomRegistry: one actor per room, opened from the database after a restart."""

import asyncio
from uuid import uuid4

import pytest

from mux.rooms import registry as registry_module
from mux.rooms.registry import RoomRegistry, get_registry, init_registry


async def publish(event):
    pass


async def test_create_then_get_returns_the_same_actor(session_factory):
    registry = RoomRegistry(publish, sessionmaker=session_factory)
    actor = await registry.create(uuid4(), "r")
    assert await registry.get(actor.room_id) is actor
    assert registry.open_rooms() == [actor.room_id]


async def test_unknown_room_is_none_and_not_kept(session_factory):
    registry = RoomRegistry(publish, sessionmaker=session_factory)
    assert await registry.get(uuid4()) is None
    assert registry.open_rooms() == []


async def test_new_registry_opens_the_room_from_the_database(session_factory):
    owner = uuid4()
    before_restart = RoomRegistry(publish, sessionmaker=session_factory)
    actor = await before_restart.create(owner, "r")
    await actor.post_message(owner, "hi")

    after_restart = RoomRegistry(publish, sessionmaker=session_factory)
    reopened = await after_restart.get(actor.room_id)
    assert reopened is not None
    assert reopened is not actor
    assert reopened.record == actor.record
    assert reopened.emitter.seq == 2


async def test_concurrent_gets_open_one_actor(session_factory):
    actor = await RoomRegistry(publish, sessionmaker=session_factory).create(uuid4(), "r")
    fresh = RoomRegistry(publish, sessionmaker=session_factory)
    opened = await asyncio.gather(*(fresh.get(actor.room_id) for _ in range(5)))
    assert opened[0] is not None
    assert all(a is opened[0] for a in opened)


def test_get_registry_needs_init(monkeypatch):
    monkeypatch.setattr(registry_module, "_registry", None)
    with pytest.raises(RuntimeError):
        get_registry()
    registry = init_registry(publish)
    assert get_registry() is registry
    