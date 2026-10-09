"""Room AI settings survive restarts and never send the key to browsers."""

import json

import pytest

import mux.rooms.registry as room_registry
from mux.events.log import InMemoryEventLog
from mux.events.wire import to_envelope
from mux.rooms.registry import RoomRegistry

MODELS = {"lightning": "fast-1", "super": "smart-1", "ultra": "smart-2"}


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logs: dict[str, InMemoryEventLog] = {}
    monkeypatch.setattr(room_registry, "get_event_log", lambda rid: logs.setdefault(rid, InMemoryEventLog(rid)))
    return RoomRegistry(), logs


async def test_ai_settings_replay_and_stay_off_the_wire(registry):
    reg, logs = registry
    actor = await reg.create_room("room_ai1", "alice", name="Docs")
    assert actor.ai_settings is None
    await actor.save_ai_settings("openai", "https://api.openai.com/v1", "ENCRYPTED-KEY", MODELS, "alice")
    first = actor.ai_settings
    assert first is not None and first["models"] == MODELS and first["version"]

    wire = json.dumps([to_envelope(e) for e in logs["room_ai1"]._events])
    assert "ENCRYPTED-KEY" not in wire and '"has_key": true' in wire

    await reg.stop_room("room_ai1")
    again = await reg.get_room_or_rehydrate("room_ai1")
    assert again is not None and again.ai_settings == first
    assert await again.clear_ai_settings("alice") is True
    assert again.ai_settings is None and await again.clear_ai_settings("alice") is False
    await reg.shutdown_all()
