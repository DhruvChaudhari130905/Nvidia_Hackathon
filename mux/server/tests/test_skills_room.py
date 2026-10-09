"""A room's enabled skills are a room event."""

import json

import pytest

import mux.rooms.registry as room_registry
from mux.events.log import InMemoryEventLog
from mux.events.wire import to_envelope
from mux.rooms.registry import RoomRegistry


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logs: dict[str, InMemoryEventLog] = {}
    monkeypatch.setattr(room_registry, "get_event_log", lambda rid: logs.setdefault(rid, InMemoryEventLog(rid)))
    return RoomRegistry(), logs


async def test_enabled_skills_replay(registry):
    reg, logs = registry
    actor = await reg.create_room("room_sk1", "alice", name="Docs")
    assert actor.skills_enabled == set()
    await actor.set_skills(["tdd", "frontend-design"], "alice")
    wire = json.dumps([to_envelope(e) for e in logs["room_sk1"]._events])
    assert '"enabled": ["frontend-design", "tdd"]' in wire
    await reg.stop_room("room_sk1")
    again = await reg.get_room_or_rehydrate("room_sk1")
    assert again is not None and again.skills_enabled == {"tdd", "frontend-design"}
    await reg.shutdown_all()
