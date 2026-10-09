"""End-to-end tests for the HTTP + WebSocket API (regression tests for the review findings)."""

import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
import jwt

import mux.rooms.registry as room_registry
from mux.config import settings
from mux.events.models import UserMessageSentEvent
from mux.main import create_app

SECRET = "test-secret-that-is-at-least-32-bytes"


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
    # Keep a developer's real .env out of these tests: no live agents, no GitHub OAuth app
    monkeypatch.setattr(settings, "token_factory_api_key", "")
    monkeypatch.setattr(settings, "github_client_id", "")
    monkeypatch.setattr(settings, "github_client_secret", "")
    monkeypatch.setattr("mux.integrations.github._github_integration", None)
    with TestClient(create_app()) as c:
        yield c


def create_room(c, owner="alice", **body) -> str:
    r = c.post("/rooms", json={"description": "demo", **body}, headers=auth(owner))
    assert r.status_code == 201, r.text
    return r.json()["id"]


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
    assert client.post("/rooms", json={"name": "x"}, headers=bad).status_code == 401


def test_messages_carry_the_senders_display_name(client):
    rid = create_room(client)
    named = jwt.encode({"sub": "alice", "aud": "authenticated", "exp": int(time.time()) + 3600, "email": "alice@x.dev",
                        "user_metadata": {"full_name": "Alice Smith"}}, SECRET, algorithm="HS256")
    r = client.post(f"/rooms/{rid}/messages", json={"text": "hi"}, headers={"Authorization": f"Bearer {named}"})
    assert r.status_code == 200, r.text
    with client.websocket_connect(f"/rooms/{rid}/ws?since=0") as ws:
        ws.send_json({"type": "auth", "payload": {"token": named}})
        dump = ws.receive_json()
    posted = next(e for e in dump if e["type"] == "message.posted")
    assert posted["payload"]["user"]["name"] == "Alice Smith"


def test_display_name_falls_back_to_email():
    from mux.auth.supabase import display_name
    assert display_name({"email": "bob@x.dev", "user_metadata": {}}) == "bob"
    assert display_name({"user_metadata": {"name": "  Bob B "}}) == "Bob B"
    assert display_name({}) is None


def test_asymmetric_supabase_token_is_verified_against_jwks(client, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from jwt.algorithms import ECAlgorithm

    import mux.auth.supabase as supa

    def es256_key():
        private = ec.generate_private_key(ec.SECP256R1())
        pem = private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        return pem, ECAlgorithm.to_jwk(private.public_key(), as_dict=True)

    signing_pem, public = es256_key()
    other_pem, _ = es256_key()
    public.update(kid="k1", alg="ES256")
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(supa, "_jwks_cache", {"url": None, "fetched_at": 0.0, "keys": []})
    monkeypatch.setattr(supa, "_fetch_jwks", lambda url: [public])

    def es_token(pem, sub="alice"):
        claims = {"sub": sub, "aud": "authenticated", "exp": int(time.time()) + 3600}
        return jwt.encode(claims, pem.decode(), algorithm="ES256", headers={"kid": "k1"})

    good = {"Authorization": f"Bearer {es_token(signing_pem)}"}
    assert client.post("/rooms", json={"description": "x"}, headers=good).status_code == 201
    forged = {"Authorization": f"Bearer {es_token(other_pem)}"}
    assert client.post("/rooms", json={"description": "x"}, headers=forged).status_code == 401


# --- rooms / permissions --------------------------------------------------

def test_room_status_and_list(client):
    rid = create_room(client)
    r = client.get(f"/rooms/{rid}", headers=auth("alice"))
    assert r.status_code == 200, r.text
    room = r.json()
    assert room["title"] == "demo" and room["owner_id"] == "alice" and room["link_access"] == "restricted"
    assert room["members"][0]["permission"] == "owner"
    assert [x["id"] for x in client.get("/rooms", headers=auth("alice")).json()] == [rid]
    assert client.get("/rooms", headers=auth("mallory")).json() == []
    assert client.get(f"/rooms/{rid}/status", headers=auth("alice")).json()["name"] == "demo"


def test_unknown_room_is_404_not_claimed(client):
    r = client.post("/api/files/room_unclaimed/files", json={"path": "a.txt", "content": "hi"}, headers=auth("mallory"))
    assert r.status_code == 404
    assert client.get("/rooms/room_unclaimed", headers=auth("mallory")).status_code == 404


def test_private_room_requires_membership(client):
    rid = create_room(client)
    assert client.post(f"/rooms/{rid}/join", json={}, headers=auth("mallory")).status_code == 403
    assert client.post(f"/api/commands/{rid}/steer", json={"instructions": "x"}, headers=auth("mallory")).status_code == 403

    r = client.post(f"/rooms/{rid}/members", json={"user_id": "bob", "role": "editor"}, headers=auth("alice"))
    assert r.status_code == 200, r.text
    r = client.post(f"/rooms/{rid}/join", json={"user_name": "Bob"}, headers=auth("bob"))
    assert r.status_code == 200, r.text
    assert client.post(f"/api/commands/{rid}/steer", json={"instructions": "x"}, headers=auth("bob")).status_code == 200
    # Leaving does not revoke membership
    client.post(f"/rooms/{rid}/leave", headers=auth("bob"))
    assert client.post(f"/api/commands/{rid}/steer", json={"instructions": "y"}, headers=auth("bob")).status_code == 200
    # Only the owner can add members
    assert client.post(f"/rooms/{rid}/members", json={"user_id": "eve"}, headers=auth("bob")).status_code == 403


def test_public_room_join_grants_editor(client):
    rid = create_room(client)
    assert client.patch(f"/rooms/{rid}/sharing", json={"link_access": "anyone"}, headers=auth("alice")).status_code == 200
    assert client.get(f"/rooms/{rid}", headers=auth("carol")).status_code == 200  # viewer
    assert client.post(f"/api/commands/{rid}/steer", json={"instructions": "x"}, headers=auth("carol")).status_code == 403
    assert client.post(f"/rooms/{rid}/join", json={}, headers=auth("carol")).status_code == 200
    assert client.post(f"/api/commands/{rid}/steer", json={"instructions": "x"}, headers=auth("carol")).status_code == 200


def test_closed_room_cannot_be_reclaimed(client):
    rid = create_room(client)
    assert client.post(f"/rooms/{rid}/close", headers=auth("alice")).status_code == 200
    assert client.get(f"/rooms/{rid}", headers=auth("mallory")).status_code == 404
    assert client.get(f"/rooms/{rid}", headers=auth("alice")).status_code == 404


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


def connect_ws(client, rid, user="alice", since=0):
    """Open the room socket and return it with the initial dump (a JSON array of envelopes)."""
    ws = client.websocket_connect(f"/rooms/{rid}/ws?since={since}&token={token(user)}").__enter__()
    dump = json.loads(ws.receive_text())
    assert isinstance(dump, list)
    return ws, dump


def test_websocket_streams_catalog_envelopes(client):
    rid = create_room(client)
    ws, dump = connect_ws(client, rid)
    try:
        assert [e["type"] for e in dump] == ["room.created"]
        assert set(dump[0]) == {"seq", "room_id", "type", "actor", "actor_id", "ts", "payload"}

        join, _ = read_until(ws, lambda m: m["type"] == "presence.join")
        assert join["payload"]["user_id"] == "alice"

        client.post(f"/rooms/{rid}/messages", json={"text": "hello", "to": "team"}, headers=auth("alice"))
        msg, _ = read_until(ws, lambda m: m["type"] == "message.posted")
        assert msg["payload"]["text"] == "hello" and msg["payload"]["to"] == "team"
        assert msg["seq"] > join["seq"]

        ws.send_text(json.dumps({"type": "presence.tab", "payload": {"tab": "nope"}}))
        err, _ = read_until(ws, lambda m: m["type"] == "error")
        assert "Invalid tab" in err["message"]

        ws.send_text(json.dumps({"type": "presence.tab", "payload": {"tab": "code"}}))
        tab, _ = read_until(ws, lambda m: m["type"] == "presence.tab")
        assert tab["payload"] == {"user_id": "alice", "tab": "code"}
        assert tab["seq"] == msg["seq"]  # ephemeral: keeps the client's resume point

        ws.send_text(json.dumps({"type": "presence.typing", "payload": {"typing": True}}))
        typing, _ = read_until(ws, lambda m: m["type"] == "presence.typing")
        assert typing["payload"] == {"user_id": "alice", "typing": True}
    finally:
        ws.__exit__(None, None, None)


def test_websocket_first_message_auth_and_resume(client):
    rid = create_room(client)
    client.post(f"/rooms/{rid}/messages", json={"text": "one"}, headers=auth("alice"))
    with client.websocket_connect(f"/rooms/{rid}/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "payload": {"token": token("alice")}}))
        dump = json.loads(ws.receive_text())
    assert [e["type"] for e in dump] == ["room.created", "message.posted"]
    seqs = [e["seq"] for e in dump]
    assert seqs == sorted(set(seqs))

    # Resuming from the last seq replays only what came after it, with no duplicates
    client.post(f"/rooms/{rid}/messages", json={"text": "two"}, headers=auth("alice"))
    ws, dump = connect_ws(client, rid, since=dump[-1]["seq"])
    try:
        texts = [e["payload"]["text"] for e in dump if e["type"] == "message.posted"]
        assert texts == ["two"]
        _, seen = read_until(ws, lambda m: m["type"] == "presence.join")
        stored = [m["seq"] for m in seen if m["type"] not in ("pong", "error", "presence.tab")]
        assert all(s > dump[-1]["seq"] for s in stored)
    finally:
        ws.__exit__(None, None, None)


def test_websocket_rejects_non_members_and_missing_tokens(client):
    from starlette.websockets import WebSocketDisconnect
    rid = create_room(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/rooms/{rid}/ws?token={token('mallory')}") as ws:
            ws.receive_text()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/rooms/{rid}/ws") as ws:
            ws.send_text(json.dumps({"type": "auth", "payload": {"token": "garbage"}}))
            ws.receive_text()


# --- the web app's REST contract ------------------------------------------

def test_file_saves_are_version_checked(client):
    rid = create_room(client)
    r = client.put(f"/rooms/{rid}/files", json={"path": "a.py", "content": "v1", "base_version": 0}, headers=auth("alice"))
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] is True and r.json()["version"] == 1
    r = client.put(f"/rooms/{rid}/files", json={"path": "a.py", "content": "v2", "base_version": 1}, headers=auth("alice"))
    assert r.json()["version"] == 2
    # An edit based on a stale version is refused instead of silently overwriting
    stale = client.put(f"/rooms/{rid}/files", json={"path": "a.py", "content": "v2b", "base_version": 1}, headers=auth("alice"))
    assert stale.status_code == 409
    assert client.get(f"/api/files/{rid}/files/a.py", headers=auth("alice")).json()["content"] == "v2"

    # Someone else's lock blocks a save
    client.post(f"/rooms/{rid}/members", json={"user_id": "bob"}, headers=auth("alice"))
    assert client.post(f"/rooms/{rid}/files/lock", json={"path": "a.py"}, headers=auth("bob")).status_code == 200
    assert client.post(f"/rooms/{rid}/files/lock", json={"path": "a.py"}, headers=auth("alice")).status_code == 409
    blocked = client.put(f"/rooms/{rid}/files", json={"path": "a.py", "content": "x", "base_version": 2}, headers=auth("alice"))
    assert blocked.status_code == 409
    assert client.post(f"/rooms/{rid}/files/unlock", json={"path": "a.py"}, headers=auth("bob")).status_code == 200

    assert client.delete(f"/rooms/{rid}/files", params={"path": "a.py"}, headers=auth("alice")).status_code == 200
    assert client.delete(f"/rooms/{rid}/files", params={"path": "a.py"}, headers=auth("alice")).status_code == 404


def test_plan_conflict_question_session_commands(client):
    rid = create_room(client, domain_role="design")
    assert client.get(f"/rooms/{rid}", headers=auth("alice")).json()["members"][0]["domain_role"] == "design"

    items = [{"id": "t1", "title": "Pricing page", "status": "draft"}, {"id": "t2", "title": "Auth", "status": "draft"}]
    r = client.patch(f"/rooms/{rid}/plan", json={"items": items}, headers=auth("alice"))
    assert r.status_code == 200 and r.json()["accepted"] is True
    assert client.post(f"/rooms/{rid}/plan/approve", headers=auth("alice")).status_code == 200
    room = registry_call(client, room_registry.get_registry().get_room, rid)
    assert {i["status"] for i in registry_call(client, room.get_plan)} == {"todo"}

    assert client.post(f"/rooms/{rid}/conflicts/c1/vote", json={"option": "SQLite"}, headers=auth("alice")).status_code == 200
    assert client.post(f"/rooms/{rid}/conflicts/c1/override", json={"option": "SQLite"}, headers=auth("alice")).status_code == 200
    assert client.post(f"/rooms/{rid}/questions/q1/answer", json={"answer": "Yes"}, headers=auth("alice")).status_code == 200
    assert client.post(f"/rooms/{rid}/end-session", headers=auth("alice")).status_code == 200

    b = client.patch(f"/rooms/{rid}/budget", json={"tokens_cap": 5_000_000}, headers=auth("alice")).json()
    assert b["tokens_cap"] == 5_000_000 and set(b) == {"tokens_used", "runs_used", "tokens_cap", "runs_cap"}

    ws, dump = connect_ws(client, rid)
    ws.__exit__(None, None, None)
    types = [e["type"] for e in dump]
    for expected in ("plan.edited", "plan.approved", "conflict.vote", "conflict.closed", "question.answered"):
        assert expected in types, types
    vote = next(e for e in dump if e["type"] == "conflict.vote")["payload"]
    assert vote == {"conflict_id": "c1", "user_id": "alice", "option": "SQLite", "weight": 1}


def test_export_needs_github(client):
    rid = create_room(client)
    r = client.post(f"/rooms/{rid}/export", json={"repo_name": "demo", "private": True}, headers=auth("alice"))
    assert r.status_code == 400 and "Connect GitHub" in r.json()["detail"]
    assert client.get("/github/connect", headers=auth("alice")).status_code == 503  # OAuth app not configured


# --- event log, rewind, rehydration ---------------------------------------

def test_rewind_restores_files_and_keeps_sequences_unique(client):
    rid = create_room(client)
    client.post(f"/api/files/{rid}/files", json={"path": "a.py", "content": "v1"}, headers=auth("alice"))
    cp = client.post(f"/api/export/{rid}/checkpoints", json={"description": "cp"}, headers=auth("alice")).json()["checkpoint_id"]
    client.put(f"/api/files/{rid}/files/a.py", json={"path": "a.py", "content": "v2"}, headers=auth("alice"))
    client.post(f"/api/files/{rid}/files", json={"path": "b.py", "content": "new"}, headers=auth("alice"))

    r = client.post(f"/rooms/{rid}/rewind", json={"checkpoint_id": cp}, headers=auth("alice"))
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
    client.post(f"/rooms/{rid}/members", json={"user_id": "bob"}, headers=auth("alice"))
    client.post(f"/api/files/{rid}/files", json={"path": "f.py", "content": "x=1"}, headers=auth("alice"))
    client.post(f"/api/export/{rid}/checkpoints", json={}, headers=auth("alice"))
    # PATCH /plan sends the whole plan (architecture.md, Q45)
    client.patch(f"/rooms/{rid}/plan", json={"items": [{"id": "p1", "title": "T", "status": "draft"},
                                                       {"id": "p2", "title": "U", "status": "doing"}]}, headers=auth("alice"))
    client.post(f"/api/commands/{rid}/approve-plan", json={"plan_item_ids": ["p1"]}, headers=auth("alice"))

    reg = room_registry.get_registry()
    registry_call(client, reg.stop_room, rid)

    # Next request rehydrates from the log; ownership and membership come from events
    r = client.get(f"/rooms/{rid}", headers=auth("bob"))
    assert r.status_code == 200, r.text
    assert r.json()["owner_id"] == "alice"
    room = registry_call(client, reg.get_room, rid)
    plan = {i["id"]: i["status"] for i in registry_call(client, room.get_plan)}
    assert plan == {"p1": "todo", "p2": "doing"}
    assert client.get(f"/api/files/{rid}/files/f.py", headers=auth("bob")).json()["content"] == "x=1"
    assert len(room.manifest.list_checkpoints()) == 1


def test_saving_a_folder_path_as_a_file_is_a_409(client):
    rid = create_room(client)
    h = auth("alice")
    assert client.put(f"/rooms/{rid}/files", json={"path": "src/App.tsx", "content": "x", "base_version": 0}, headers=h).status_code == 200
    r = client.put(f"/rooms/{rid}/files", json={"path": "src", "content": "", "base_version": 0}, headers=h)
    assert r.status_code == 409 and "folder" in r.json()["detail"]
    r = client.put(f"/rooms/{rid}/files", json={"path": "src/App.tsx/x", "content": "", "base_version": 0}, headers=h)
    assert r.status_code == 409 and "is a file" in r.json()["detail"]


def test_rooms_survive_a_server_restart(client):
    """Events are kept on disk: after a restart the room is listed again and rebuilt with its state."""
    import mux.main as main_module

    rid = create_room(client, initial_plan=[{"id": "p1", "title": "Home page", "status": "draft"}])
    client.post(f"/rooms/{rid}/messages", json={"text": "make it blue"}, headers=auth("alice"))
    client.put(f"/rooms/{rid}/files", json={"path": "index.html", "content": "<h1>hi</h1>", "base_version": 0}, headers=auth("alice"))
    client.post(f"/rooms/{rid}/plan/approve", headers=auth("alice"))

    # A restart: no running actors and no cached logs, only what's on disk
    registry_call(client, room_registry.get_registry().stop_room, rid)
    main_module._room_event_logs.clear()

    assert [r["id"] for r in client.get("/rooms", headers=auth("alice")).json()] == [rid]
    assert client.get("/rooms", headers=auth("mallory")).json() == []
    room = registry_call(client, room_registry.get_registry().get_room, rid)
    assert [(p["title"], p["status"]) for p in registry_call(client, room.get_plan)] == [("Home page", "todo")]
    assert client.get(f"/api/files/{rid}/files/index.html", headers=auth("alice")).json()["content"] == "<h1>hi</h1>"
    with client.websocket_connect(f"/rooms/{rid}/ws?since=0") as ws:
        ws.send_json({"type": "auth", "payload": {"token": token("alice")}})
        dump = ws.receive_json()
    assert any(e["type"] == "message.posted" and e["payload"]["text"] == "make it blue" for e in dump)


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
    r = client.get("/api/export/github/callback", params={"code": "c", "state": forged}, follow_redirects=False)
    assert r.status_code == 307 and "github=error" in r.headers["location"]


def test_connect_github_then_export_creates_the_repo(client, monkeypatch):
    """The callback records the GitHub login, and export creates a missing repo before pushing."""
    from mux.integrations.github import get_github_integration

    monkeypatch.setattr(settings, "web_app_url", "http://app.test")
    gh = get_github_integration()
    gh.config.client_id, gh.config.client_secret = "id", "secret"
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        path = req.url.path
        if path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "tok", "scope": "repo"})
        if path == "/user":
            return httpx.Response(200, json={"login": "alice-gh", "id": 7, "email": "a@x.dev"})
        if path == "/repos/alice-gh/shop" and req.method == "GET":
            return httpx.Response(404 if ("POST", "/user/repos") not in calls else 200, json={"default_branch": "main"})
        if path == "/user/repos":
            assert json.loads(req.content)["private"] is False
            return httpx.Response(201, json={})
        if path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "base"}})
        if path.endswith("/git/commits/base"):
            return httpx.Response(200, json={"tree": {"sha": "tree0"}})
        if path.endswith("/git/blobs"):
            return httpx.Response(201, json={"sha": "blob"})
        if path.endswith("/git/trees"):
            return httpx.Response(201, json={"sha": "tree1"})
        if path.endswith("/git/commits"):
            return httpx.Response(201, json={"sha": "c1"})
        if path.endswith("/git/refs/heads/main"):
            return httpx.Response(200, json={})
        return httpx.Response(500, json={"unexpected": path})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: real(transport=httpx.MockTransport(handler)))

    rid = create_room(client)
    client.put(f"/rooms/{rid}/files", json={"path": "index.html", "content": "<h1>hi</h1>", "base_version": 0}, headers=auth("alice"))
    _, state = gh.get_authorization_url("alice")
    r = client.get("/api/export/github/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert r.headers["location"] == "http://app.test/profile?github=connected&username=alice-gh"

    r = client.post(f"/rooms/{rid}/export", json={"repo_name": "shop", "private": False}, headers=auth("alice"))
    assert r.status_code == 200, r.text
    assert r.json()["url"] == "https://github.com/alice-gh/shop/commit/c1"
    assert ("POST", "/user/repos") in calls


def test_github_connect_returns_to_the_page_that_started_it(client, monkeypatch):
    from urllib.parse import parse_qs, urlparse

    from mux.integrations.github import get_github_integration

    monkeypatch.setattr(settings, "web_app_url", "http://app.test")
    gh = get_github_integration()
    gh.config.client_id = "id"

    def state_for(next_path):
        r = client.get("/github/connect", params={"next": next_path}, headers=auth("alice"))
        return parse_qs(urlparse(r.json()["url"]).query)["state"][0]

    # A bad state still goes back to where the user came from, with the error
    state = state_for("/room/r1?export=1")
    monkeypatch.setattr(gh, "exchange_code_for_token", lambda code, state: (_ for _ in ()).throw(ValueError("bad code")))
    r = client.get("/api/export/github/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert r.headers["location"].startswith("http://app.test/room/r1?export=1&github=error")

    # Paths that would leave the app fall back to the profile page
    for unsafe in ("https://evil.test/x", "//evil.test/x", "/\\evil.test"):
        state = state_for(unsafe)
        r = client.get("/api/export/github/callback", params={"code": "c", "state": state}, follow_redirects=False)
        assert r.headers["location"].startswith("http://app.test/profile?github=error"), unsafe


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
async def test_emit_event_sends_envelope_once_per_connection(monkeypatch):
    from mux.api import ws as ws_module
    from mux.events.bus import EventBus

    class FakeSocket:
        def __init__(self):
            self.sent = []

        async def send_text(self, data: str) -> None:
            self.sent.append(json.loads(data))

    bus = EventBus()
    monkeypatch.setattr(ws_module, "event_bus", bus)
    fresh, caught_up = FakeSocket(), FakeSocket()
    bus.connect("r", fresh, last_seq=0)
    bus.connect("r", caught_up, last_seq=1)  # already had seq 1 in its initial dump

    event = UserMessageSentEvent(room_id="r", sequence=1, message_id="m1", content="hi", user_id="u")
    await ws_module.emit_event("r", event)
    await ws_module.emit_event("r", event)  # a late duplicate broadcast is dropped
    assert [m["type"] for m in fresh.sent] == ["message.posted"]
    assert fresh.sent[0]["payload"]["text"] == "hi" and fresh.sent[0]["seq"] == 1
    assert caught_up.sent == []


def test_every_mapped_event_has_a_catalog_type():
    """Every envelope type the server can send is one the web app knows (web/src/types/index.ts)."""
    import inspect
    import re
    from pathlib import Path
    import mux.events.models as models
    from mux.events.wire import to_envelope

    ts_types = Path(__file__).resolve().parents[2] / "web" / "src" / "types" / "index.ts"
    known = set(re.findall(r"\| '([a-z_.]+)'", ts_types.read_text()))
    wire_src = (Path(models.__file__).parent / "wire.py").read_text()
    sent = set(re.findall(r'return "([a-z_.]+)", ', wire_src))
    assert sent and sent <= known, sent - known
    assert inspect.isfunction(to_envelope)


def test_only_the_owner_can_delete_a_room_and_it_leaves_the_list(client):
    rid = create_room(client)
    assert client.post(f"/rooms/{rid}/close", headers=auth("bob")).status_code in (403, 404)
    assert rid in [r["id"] for r in client.get("/rooms", headers=auth("alice")).json()]

    r = client.post(f"/rooms/{rid}/close", params={"reason": "deleted_by_owner"}, headers=auth("alice"))
    assert r.status_code == 200 and r.json()["closed"] is True
    assert rid not in [r["id"] for r in client.get("/rooms", headers=auth("alice")).json()]
