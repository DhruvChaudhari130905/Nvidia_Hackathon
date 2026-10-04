"""End-to-end tests for the HTTP + WebSocket API (regression tests for the review findings)."""

import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from jose import jwt

import mux.rooms.registry as room_registry
from mux.config import settings
from mux.events.models import EventType, UserMessageSentEvent
from mux.main import create_app

SECRET = "test-secret"


def token(sub: str, aud: str | None = "authenticated") -> str:
    """A Supabase-shaped access token (Supabase sets aud='authenticated')."""
    payload = {"sub": sub, "role": "authenticated", "exp": int(time.time()) + 3600}
    if aud:
        payload["aud"] = aud
    return jwt.encode(payload, SECRET, algorithm="HS256")


def auth(sub: str) -> dict:
    return {"Authorization": f"Bearer {token(sub)}"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # FileStore and sqlite live under cwd
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "supabase_jwt_audience", "")
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    with TestClient(create_app()) as c:
        yield c


def create_room(c, owner="alice", **body) -> str:
    r = c.post("/api/rooms", json={"name": "demo", **body}, headers=auth(owner))
    assert r.status_code == 201, r.text
    return r.json()["room_id"]


def registry_call(c, fn, *args):
    return c.portal.call(fn, *args)


# --- startup / auth -------------------------------------------------------

def test_app_starts(client):
    assert client.get("/health").json() == {"status": "healthy"}


def test_supabase_token_with_aud_is_accepted(client):
    create_room(client)  # token carries aud="authenticated"


def test_configured_audience_is_enforced(client, monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")
    create_room(client)
    bad = {"Authorization": f"Bearer {token('alice', aud='other')}"}
    assert client.post("/api/rooms", json={"name": "x"}, headers=bad).status_code == 401


# --- rooms / permissions --------------------------------------------------

def test_room_status_and_list(client):
    rid = create_room(client)
    r = client.get(f"/api/rooms/{rid}", headers=auth("alice"))
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "demo"
    assert [x["room_id"] for x in client.get("/api/rooms", headers=auth("alice")).json()["rooms"]] == [rid]
    assert client.get("/api/rooms", headers=auth("mallory")).json()["rooms"] == []


def test_unknown_room_is_404_not_claimed(client):
    r = client.post("/api/files/room_unclaimed/files", json={"path": "a.txt", "content": "hi"}, headers=auth("mallory"))
    assert r.status_code == 404
    assert client.get("/api/rooms/room_unclaimed", headers=auth("mallory")).status_code == 404


def test_private_room_requires_membership(client):
    rid = create_room(client)
    assert client.post(f"/api/rooms/{rid}/join", json={}, headers=auth("mallory")).status_code == 403
    assert client.post(f"/api/commands/{rid}/steer", json={"instructions": "x"}, headers=auth("mallory")).status_code == 403

    r = client.post(f"/api/rooms/{rid}/members", json={"user_id": "bob", "role": "editor"}, headers=auth("alice"))
    assert r.status_code == 200, r.text
    r = client.post(f"/api/rooms/{rid}/join", json={"user_name": "Bob"}, headers=auth("bob"))
    assert r.status_code == 200, r.text
    assert client.post(f"/api/commands/{rid}/steer", json={"instructions": "x"}, headers=auth("bob")).status_code == 200
    # Leaving does not revoke membership
    client.post(f"/api/rooms/{rid}/leave", headers=auth("bob"))
    assert client.post(f"/api/commands/{rid}/steer", json={"instructions": "y"}, headers=auth("bob")).status_code == 200
    # Only the owner can add members
    assert client.post(f"/api/rooms/{rid}/members", json={"user_id": "eve"}, headers=auth("bob")).status_code == 403


def test_public_room_join_grants_editor(client):
    rid = create_room(client)
    assert client.patch(f"/api/rooms/{rid}/sharing", json={"public": True}, headers=auth("alice")).status_code == 200
    assert client.get(f"/api/rooms/{rid}", headers=auth("carol")).status_code == 200  # viewer
    assert client.post(f"/api/commands/{rid}/steer", json={"instructions": "x"}, headers=auth("carol")).status_code == 403
    assert client.post(f"/api/rooms/{rid}/join", json={}, headers=auth("carol")).status_code == 200
    assert client.post(f"/api/commands/{rid}/steer", json={"instructions": "x"}, headers=auth("carol")).status_code == 200


def test_closed_room_cannot_be_reclaimed(client):
    rid = create_room(client)
    assert client.post(f"/api/rooms/{rid}/close", headers=auth("alice")).status_code == 200
    assert client.get(f"/api/rooms/{rid}", headers=auth("mallory")).status_code == 404
    assert client.get(f"/api/rooms/{rid}", headers=auth("alice")).status_code == 404


def test_invalid_plan_edit_is_400_and_atomic(client):
    rid = create_room(client, initial_plan=[{"id": "p1", "title": "T", "status": "draft"}])
    edits = [{"type": "update", "item_id": "p1", "changes": {"status": "doing"}},
             {"type": "update", "item_id": "nope", "changes": {"status": "done"}}]
    r = client.post(f"/api/commands/{rid}/edit-plan", json={"edits": edits}, headers=auth("alice"))
    assert r.status_code == 400
    room = registry_call(client, room_registry.get_registry().get_room, rid)
    assert registry_call(client, room.get_plan)[0]["status"] == "draft"


def test_raise_budget_without_increase_is_400(client):
    rid = create_room(client)
    r = client.post(f"/api/commands/{rid}/raise-budget", json={"token_cap": 1}, headers=auth("alice"))
    assert r.status_code == 400


# --- files ----------------------------------------------------------------

def test_files_are_isolated_per_room(client):
    a = create_room(client, owner="alice")
    b = create_room(client, owner="bob")
    client.post(f"/api/files/{a}/files", json={"path": "src/app.py", "content": "alice"}, headers=auth("alice"))
    client.post(f"/api/files/{b}/files", json={"path": "src/app.py", "content": "bob"}, headers=auth("bob"))
    assert client.get(f"/api/files/{a}/files/src/app.py", headers=auth("alice")).json()["content"] == "alice"


def test_file_metadata_lock_status_and_duplicates(client):
    rid = create_room(client)
    r = client.post(f"/api/files/{rid}/files", json={"path": "/app.py", "content": "x"}, headers=auth("alice"))
    assert r.json()["path"] == "app.py"
    assert client.post(f"/api/files/{rid}/files", json={"path": "app.py", "content": "y"}, headers=auth("alice")).status_code == 409

    listing = client.get(f"/api/files/{rid}/files", headers=auth("alice")).json()["files"]
    assert listing[0]["file_type"] == "text/x-python"

    client.post(f"/api/files/{rid}/files/app.py/lock", headers=auth("alice"))
    r = client.get(f"/api/files/{rid}/files/app.py/lock", headers=auth("alice"))
    assert r.status_code == 200, r.text
    assert r.json()["locked_by"] == "alice"


def test_deleted_file_is_not_readable(client):
    rid = create_room(client)
    client.post(f"/api/files/{rid}/files", json={"path": "a.txt", "content": "x"}, headers=auth("alice"))
    assert client.delete(f"/api/files/{rid}/files/a.txt", headers=auth("alice")).status_code == 200
    assert client.get(f"/api/files/{rid}/files/a.txt", headers=auth("alice")).status_code == 404


# --- websocket ------------------------------------------------------------

def read_until(ws, predicate, max_rounds=20):
    """Read messages until one matches.

    Each round sends a ping; reaching its pong without a match gives the server's
    broadcast tasks another chance to run. After max_rounds the message is treated
    as never sent (fails fast instead of blocking forever on receive)."""
    seen = []
    for _ in range(max_rounds):
        ws.send_text(json.dumps({"type": "ping"}))
        while True:
            msg = json.loads(ws.receive_text())
            seen.append(msg)
            if predicate(msg):
                return msg, seen
            if msg["type"] == "pong":
                break
    raise AssertionError(f"not found in {[m['type'] for m in seen]}")


def test_websocket_receives_actor_events_and_aliases(client):
    rid = create_room(client)
    with client.websocket_connect(f"/ws/rooms/{rid}?token={token('alice')}") as ws:
        read_until(ws, lambda m: m["type"] == "user_joined")
        client.post(f"/api/rooms/{rid}/messages", json={"content": "hello"}, headers=auth("alice"))
        msg, _ = read_until(ws, lambda m: m["type"] == "message.posted")
        assert msg["content"] == "hello"

        ws.send_text(json.dumps({"type": "presence", "status": "busy"}))
        err, _ = read_until(ws, lambda m: m["type"] == "error")
        assert "Invalid status" in err["message"]

        ws.send_text(json.dumps({"type": "presence", "typing": True}))
        upd, _ = read_until(ws, lambda m: m["type"] == "presence_update")
        assert upd["typing"] is True


def test_websocket_rejects_non_members(client):
    from starlette.websockets import WebSocketDisconnect
    rid = create_room(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/rooms/{rid}?token={token('mallory')}") as ws:
            ws.receive_text()


# --- event log, rewind, rehydration ---------------------------------------

def test_rewind_restores_files_and_keeps_sequences_unique(client):
    rid = create_room(client)
    client.post(f"/api/files/{rid}/files", json={"path": "a.py", "content": "v1"}, headers=auth("alice"))
    cp = client.post(f"/api/export/{rid}/checkpoints", json={"description": "cp"}, headers=auth("alice")).json()["checkpoint_id"]
    client.put(f"/api/files/{rid}/files/a.py", json={"path": "a.py", "content": "v2"}, headers=auth("alice"))
    client.post(f"/api/files/{rid}/files", json={"path": "b.py", "content": "new"}, headers=auth("alice"))

    r = client.post(f"/api/rooms/{rid}/rewind", json={"checkpoint_id": cp}, headers=auth("alice"))
    assert r.status_code == 200, r.text
    assert client.get(f"/api/files/{rid}/files/a.py", headers=auth("alice")).json()["content"] == "v1"
    assert client.get(f"/api/files/{rid}/files/b.py", headers=auth("alice")).status_code == 404

    room = registry_call(client, room_registry.get_registry().get_room, rid)
    seqs = [e.sequence for e in room.event_log._events]
    assert seqs == list(range(1, len(seqs) + 1))
    # Checkpoints survive the rewind (the original plus the pre-rewind one)
    assert len(client.get(f"/api/export/{rid}/checkpoints", headers=auth("alice")).json()["checkpoints"]) == 2


def test_rehydration_restores_state(client):
    rid = create_room(client, initial_plan=[{"id": "p1", "title": "T", "status": "draft"}])
    client.post(f"/api/rooms/{rid}/members", json={"user_id": "bob"}, headers=auth("alice"))
    client.post(f"/api/files/{rid}/files", json={"path": "f.py", "content": "x=1"}, headers=auth("alice"))
    client.post(f"/api/export/{rid}/checkpoints", json={}, headers=auth("alice"))
    client.patch(f"/api/rooms/{rid}/plan", json={"items": [{"id": "p2", "title": "U", "status": "doing"}]}, headers=auth("alice"))
    client.post(f"/api/commands/{rid}/approve-plan", json={"plan_item_ids": ["p1"]}, headers=auth("alice"))

    reg = room_registry.get_registry()
    registry_call(client, reg.stop_room, rid)

    # Next request rehydrates from the log; ownership and membership come from events
    r = client.get(f"/api/rooms/{rid}", headers=auth("bob"))
    assert r.status_code == 200, r.text
    assert r.json()["owner_id"] == "alice"
    room = registry_call(client, reg.get_room, rid)
    plan = {i["id"]: i["status"] for i in registry_call(client, room.get_plan)}
    assert plan == {"p1": "todo", "p2": "doing"}
    assert client.get(f"/api/files/{rid}/files/f.py", headers=auth("bob")).json()["content"] == "x=1"
    assert len(room.manifest.list_checkpoints()) == 1


def test_rehydration_restores_budget(client):
    rid = create_room(client)
    reg = room_registry.get_registry()
    room = registry_call(client, reg.get_room, rid)
    registry_call(client, room.record_tokens, 2_000_000, "alice")
    assert client.get(f"/api/commands/{rid}/budget", headers=auth("alice")).json()["paused"] is True
    client.post(f"/api/commands/{rid}/raise-budget", json={"token_cap": 3_000_000}, headers=auth("alice"))

    registry_call(client, reg.stop_room, rid)
    status = client.get(f"/api/commands/{rid}/budget", headers=auth("alice")).json()
    assert status["paused"] is False
    assert status["tokens_used"] == 2_000_000


# --- GitHub ---------------------------------------------------------------

def test_github_callback_rejects_forged_state(client):
    import base64
    forged = base64.urlsafe_b64encode(json.dumps({"user_id": "victim"}).encode()).decode()
    r = client.get("/api/export/github/callback", params={"code": "c", "state": forged})
    assert r.status_code == 400


def test_github_state_is_single_use():
    from mux.integrations.github import GitHubIntegration
    gh = GitHubIntegration()
    gh.config.client_id = "id"
    _, state = gh.get_authorization_url("alice")
    assert gh.consume_state(state) == "alice"
    assert gh.consume_state(state) is None


@pytest.mark.asyncio
async def test_github_user_info_with_private_email(monkeypatch):
    from mux.integrations.github import GitHubIntegration

    def handler(req):
        if req.url.path == "/user":
            return httpx.Response(200, json={"login": "a", "id": 1, "email": None})
        return httpx.Response(200, json=[{"email": "a@x.dev", "primary": True, "verified": True}])

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: real(transport=httpx.MockTransport(handler)))
    info = await GitHubIntegration().get_user_info("t")
    assert info.email == "a@x.dev"


# --- units ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_alias_event_keeps_payload(monkeypatch):
    from mux.api import ws as ws_module
    sent = []

    async def capture_event(room_id, event):
        sent.append(json.loads(event.model_dump_json()))

    async def capture_json(room_id, message):
        sent.append(message)

    monkeypatch.setattr(ws_module.event_bus, "publish", capture_event)
    monkeypatch.setattr(ws_module.event_bus, "publish_json", capture_json)
    event = UserMessageSentEvent(room_id="r", sequence=1, message_id="m1", content="hi", user_id="u")
    await ws_module.emit_event_with_alias("r", event)
    assert [m["type"] for m in sent] == [EventType.USER_MESSAGE_SENT.value, EventType.MESSAGE_POSTED.value]
    assert sent[1]["content"] == "hi"
