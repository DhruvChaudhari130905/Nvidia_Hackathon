"""REST API: sign-in, rooms, join and sharing, permission checks, messages, plan, cards, files, checkpoints, budget."""

import time
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
import jwt

from mux.api.deps import user_from_token
from mux.config import settings
from mux.events.bus import event_bus
from mux.events.models import PlanItem
from mux.main import create_app
from mux.rooms.registry import get_registry, init_registry

SECRET = "test-secret-that-is-32-bytes-long!"


def token(user_id: UUID | str, name: str = "Ada") -> str:
    claims = {"sub": str(user_id), "exp": int(time.time()) + 600, "user_metadata": {"full_name": name}}
    return jwt.encode(claims, SECRET, algorithm="HS256")


def auth(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(user_id)}"}


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "supabase_jwt_audience", "")
    monkeypatch.setattr(settings, "supabase_jwt_issuer", "")
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "allow_unverified_tokens", False)


@pytest.fixture
async def client(session_factory) -> AsyncIterator[AsyncClient]:
    """The app with a registry on the test database. ASGITransport skips the lifespan, so the fixture
    starts and closes the registry itself."""
    registry = init_registry(event_bus.publish, sessionmaker=session_factory)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c
    await registry.close()


async def new_room(client: AsyncClient, owner: UUID) -> str:
    r = await client.post("/api/rooms", json={"title": "r"}, headers=auth(owner))
    assert r.status_code == 201
    return r.json()["id"]


def test_user_from_token():
    user_id = uuid4()
    user = user_from_token(token(user_id, "Ada"))
    assert user is not None
    assert (user.id, user.name) == (user_id, "Ada")
    assert user_from_token(None) is None
    assert user_from_token("not-a-jwt") is None
    assert user_from_token(token("not-a-uuid")) is None


async def test_every_route_needs_a_token(client):
    assert (await client.get("/api/rooms")).status_code == 401
    assert (await client.get("/api/rooms", headers={"Authorization": "Bearer nope"})).status_code == 401


async def test_create_list_and_get(client):
    owner = uuid4()
    r = await client.post("/api/rooms", json={"title": "r", "domain_role": "eng"}, headers=auth(owner))
    room = r.json()
    assert (room["my_permission"], room["last_seq"]) == ("owner", 2)  # room.created, checkpoint.created
    assert room["members"] == [{"user_id": str(owner), "permission": "owner", "domain_role": "eng"}]
    assert room["head_checkpoint_id"] is not None
    listed = (await client.get("/api/rooms", headers=auth(owner))).json()
    assert [(x["id"], x["permission"]) for x in listed] == [(room["id"], "owner")]
    assert (listed[0]["members"], listed[0]["budget_runs_cap"]) == (room["members"], room["budget_runs_cap"])
    assert (await client.get(f"/api/rooms/{room['id']}", headers=auth(owner))).json() == room
    assert (await client.get(f"/api/rooms/{uuid4()}", headers=auth(owner))).status_code == 404


async def test_a_private_room_is_hidden_until_its_link_opens(client):
    owner, guest = uuid4(), uuid4()
    room = await new_room(client, owner)
    assert (await client.get(f"/api/rooms/{room}", headers=auth(guest))).status_code == 404
    assert (await client.post(f"/api/rooms/{room}/join", headers=auth(guest))).status_code == 403

    sharing = {"link_access": "anyone", "link_permission": "viewer"}
    assert (await client.put(f"/api/rooms/{room}/sharing", json=sharing, headers=auth(guest))).status_code == 404
    assert (await client.put(f"/api/rooms/{room}/sharing", json=sharing, headers=auth(owner))).status_code == 204
    r = await client.post(f"/api/rooms/{room}/join", json={"domain_role": "design"}, headers=auth(guest))
    assert r.json() == {"permission": "viewer"}
    assert (await client.get(f"/api/rooms/{room}", headers=auth(guest))).json()["my_permission"] == "viewer"
    r = await client.post(f"/api/rooms/{room}/messages", json={"text": "hi"}, headers=auth(guest))
    assert r.status_code == 403  # viewers read only


async def test_an_open_link_needs_a_permission(client):
    owner = uuid4()
    room = await new_room(client, owner)
    r = await client.put(f"/api/rooms/{room}/sharing", json={"link_access": "anyone"}, headers=auth(owner))
    assert r.status_code == 400


async def test_owner_adds_an_editor_who_cannot_do_owner_things(client):
    owner, editor = uuid4(), uuid4()
    room = await new_room(client, owner)
    r = await client.put(f"/api/rooms/{room}/members/{editor}", json={"permission": "editor"}, headers=auth(owner))
    assert r.status_code == 204
    r = await client.post(f"/api/rooms/{room}/messages", json={"text": "hi", "to": "team"}, headers=auth(editor))
    assert r.status_code == 201
    assert (r.json()["text"], r.json()["to"], r.json()["user_id"]) == ("hi", "team", str(editor))
    assert (await client.post(f"/api/rooms/{room}/plan/approve", headers=auth(editor))).status_code == 403
    r = await client.put(f"/api/rooms/{room}/members/{owner}", json={"permission": "viewer"}, headers=auth(owner))
    assert r.status_code == 400  # the owner's permission cannot change


async def test_plan_edit_approve_and_update(client):
    owner = uuid4()
    room = await new_room(client, owner)
    items = {"items": [{"id": "t1", "title": "Login page"}]}
    assert (await client.put(f"/api/rooms/{room}/plan", json=items, headers=auth(owner))).status_code == 204
    assert (await client.post(f"/api/rooms/{room}/plan/approve", headers=auth(owner))).status_code == 204
    assert (await client.post(f"/api/rooms/{room}/plan/approve", headers=auth(owner))).status_code == 400  # no drafts
    r = await client.post(f"/api/rooms/{room}/plan/items", json={"id": "t2", "title": "Tests"}, headers=auth(owner))
    assert r.status_code == 204
    r = await client.patch(f"/api/rooms/{room}/plan/items/t2", json={"title": "More tests"}, headers=auth(owner))
    assert r.status_code == 204
    r = await client.patch(f"/api/rooms/{room}/plan/items/nope", json={"title": "x"}, headers=auth(owner))
    assert r.status_code == 400


async def test_files_lock_save_and_read(client):
    owner, editor = uuid4(), uuid4()
    room = await new_room(client, owner)
    await client.put(f"/api/rooms/{room}/members/{editor}", json={"permission": "editor"}, headers=auth(owner))
    new = {"content": "hi", "base_version": None}

    assert (await client.put(f"/api/rooms/{room}/files/src/a.ts", json=new, headers=auth(editor))).status_code == 409
    assert (await client.post(f"/api/rooms/{room}/locks/src/a.ts", headers=auth(editor))).status_code == 204
    assert (await client.post(f"/api/rooms/{room}/locks/src/a.ts", headers=auth(owner))).status_code == 409
    r = await client.put(f"/api/rooms/{room}/files/src/a.ts", json=new, headers=auth(editor))
    assert r.json() == {"path": "src/a.ts", "version": 1, "changed": True}
    r = await client.put(f"/api/rooms/{room}/files/src/a.ts", json=new, headers=auth(editor))
    assert r.status_code == 409
    assert r.json()["detail"]["version"] == 1  # stale base_version

    r = await client.get(f"/api/rooms/{room}/files/src/a.ts", headers=auth(owner))
    assert r.json() == {"path": "src/a.ts", "version": 1, "content": "hi"}
    assert {"path": "src/a.ts", "version": 1} in (await client.get(f"/api/rooms/{room}/files", headers=auth(owner))).json()
    assert (await client.get(f"/api/rooms/{room}/files/nope.ts", headers=auth(owner))).status_code == 404

    assert (await client.delete(f"/api/rooms/{room}/locks/src/a.ts", headers=auth(owner))).status_code == 204  # force
    r = await client.put(f"/api/rooms/{room}/files/src/a.ts", json={"content": "x", "base_version": 1}, headers=auth(editor))
    assert r.status_code == 409  # the lock is gone


async def test_checkpoint_and_rewind(client):
    owner = uuid4()
    room = await new_room(client, owner)
    [c0] = (await client.get(f"/api/rooms/{room}/checkpoints", headers=auth(owner))).json()
    r = await client.post(f"/api/rooms/{room}/checkpoints", headers=auth(owner))
    assert r.status_code == 201
    assert (r.json()["parent_id"], r.json()["head"]) == (c0["id"], True)
    r = await client.post(f"/api/rooms/{room}/rewind", json={"checkpoint_id": c0["id"]}, headers=auth(owner))
    assert r.json() == {"checkpoint_id": c0["id"], "log": None}
    heads = [cp["id"] for cp in (await client.get(f"/api/rooms/{room}/checkpoints", headers=auth(owner))).json() if cp["head"]]
    assert heads == [c0["id"]]
    r = await client.post(f"/api/rooms/{room}/rewind", json={"checkpoint_id": str(uuid4())}, headers=auth(owner))
    assert r.status_code == 404


async def test_budget_caps_and_end_session(client):
    owner = uuid4()
    room = await new_room(client, owner)
    r = await client.put(f"/api/rooms/{room}/budget", json={"tokens_cap": 1000, "runs_cap": 10}, headers=auth(owner))
    assert r.json() == {"tokens_used": 0, "runs_used": 0, "tokens_cap": 1000, "runs_cap": 10, "paused": False}
    assert (await client.get(f"/api/rooms/{room}/budget", headers=auth(owner))).json()["tokens_cap"] == 1000
    r = await client.put(f"/api/rooms/{room}/budget", json={"tokens_cap": 0, "runs_cap": 10}, headers=auth(owner))
    assert r.status_code == 422
    assert (await client.post(f"/api/rooms/{room}/session/end", headers=auth(owner))).json() == {"ended": False}


async def test_cards_vote_override_and_answer(client):
    owner, mate, viewer = uuid4(), uuid4(), uuid4()
    room_id = await new_room(client, owner)
    for user, permission in ((mate, "editor"), (viewer, "viewer")):
        r = await client.put(f"/api/rooms/{room_id}/members/{user}", json={"permission": permission}, headers=auth(owner))
        assert r.status_code == 204
    actor = await get_registry().get(UUID(room_id))
    assert actor is not None
    await actor.draft_plan([PlanItem(id="t1", title="Checkout", status="todo")], "owner")
    card = await actor.open_conflict([], "A or B?", ["A", "B"], "ui", "use B")
    await actor.start_vote(card.id)
    question = await actor.open_question("t1", "Stripe?", ["Yes", "No"], "No")

    vote = f"/api/rooms/{room_id}/conflicts/{card.id}/vote"
    assert (await client.post(vote, json={"option": "A"}, headers=auth(viewer))).status_code == 403
    assert (await client.post(vote, json={"option": "C"}, headers=auth(mate))).status_code == 400
    assert (await client.post(vote, json={"option": "A"}, headers=auth(mate))).status_code == 204
    missing = f"/api/rooms/{room_id}/conflicts/{uuid4()}/vote"
    assert (await client.post(missing, json={"option": "A"}, headers=auth(mate))).status_code == 404
    override = f"/api/rooms/{room_id}/conflicts/{card.id}/override"
    assert (await client.post(override, json={"option": "B"}, headers=auth(mate))).status_code == 403
    assert (await client.post(override, json={"option": "B"}, headers=auth(owner))).status_code == 204
    answer = f"/api/rooms/{room_id}/questions/{question.id}/answer"
    assert (await client.post(answer, json={"answer": "Yes"}, headers=auth(mate))).status_code == 204

    cards = (await client.get(f"/api/rooms/{room_id}/cards", headers=auth(viewer))).json()
    [conflict], [asked] = cards["conflicts"], cards["questions"]
    assert (conflict["result"], conflict["resolved_by"], conflict["votes"]) == ("B", "override", {str(mate): "A"})
    assert (asked["answer"], asked["defaulted"]) == ("Yes", False)
