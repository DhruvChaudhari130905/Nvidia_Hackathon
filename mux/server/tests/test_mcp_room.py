"""MCP settings are room events: they survive restarts and never send token values to browsers."""

import json

import pytest

import mux.rooms.registry as room_registry
from mux.events.log import InMemoryEventLog
from mux.events.wire import to_envelope
from mux.rooms.registry import RoomRegistry

TOOLS = [{"name": "add", "description": "Add", "input_schema": {"type": "object"}}]


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logs: dict[str, InMemoryEventLog] = {}
    monkeypatch.setattr(room_registry, "get_event_log", lambda rid: logs.setdefault(rid, InMemoryEventLog(rid)))
    return RoomRegistry(), logs


async def test_mcp_settings_replay_and_stay_off_the_wire(registry):
    reg, logs = registry
    actor = await reg.create_room("room_mcp1", "alice", name="Docs")
    await actor.save_mcp_server("docs", "https://93.184.216.34/mcp", {"Authorization": "ENCRYPTED-VALUE"}, TOOLS,
                                {"add": {"enabled": True, "mode": "ask"}}, "alice")
    await actor.save_mcp_server("old", "https://93.184.216.34/old", {}, [], {}, "alice")
    assert await actor.remove_mcp_server("old", "alice") is True
    assert await actor.remove_mcp_server("old", "alice") is False
    await actor.set_mcp_admin("github", True, {"create_issue": {"enabled": True, "mode": "ask"}}, "alice")

    wire = json.dumps([to_envelope(e) for e in logs["room_mcp1"]._events])
    assert "ENCRYPTED-VALUE" not in wire and '"header_names": ["Authorization"]' in wire
    assert wire.count('"type": "mcp.changed"') == 4

    await reg.stop_room("room_mcp1")
    again = await reg.get_room_or_rehydrate("room_mcp1")
    assert again is not None
    assert list(again.mcp_servers) == ["docs"]
    assert again.mcp_servers["docs"]["headers"] == {"Authorization": "ENCRYPTED-VALUE"}
    assert again.mcp_servers["docs"]["settings"]["add"]["mode"] == "ask"
    assert again.mcp_admin == {"github": {"enabled": True, "settings": {"create_issue": {"enabled": True, "mode": "ask"}}}}
    await reg.shutdown_all()
