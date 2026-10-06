"""GitHub connect and export, against a fake GitHub API (httpx.MockTransport)."""

import base64
import json
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from mux.api import github as github_routes
from mux.config import settings
from mux.db.tables import GithubToken
from mux.events.bus import event_bus
from mux.integrations.github import GitHub
from mux.main import create_app
from mux.rooms.registry import init_registry
from tests.test_api import auth, jwt_secret, new_room  # noqa: F401  (jwt_secret is an autouse fixture)

TOKEN = "gho_secret"


class FakeGitHub:
    """Just enough of github.com and api.github.com for one connect and one export."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.repos: set[str] = {"taken"}
        self.blobs: dict[str, bytes] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        is_json = request.headers.get("content-type", "").startswith("application/json")
        body = json.loads(request.content) if is_json else {}
        if path == "/login/oauth/access_token":
            form = parse_qs(request.content.decode())
            if form["code"] == ["good"]:
                return httpx.Response(200, json={"access_token": TOKEN, "scope": "repo"})
            return httpx.Response(200, json={"error": "bad_verification_code"})
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401)
        if path == "/user":
            return httpx.Response(200, json={"login": "ada"})
        if path == "/user/repos":
            if body["name"] in self.repos:
                return httpx.Response(422, json={"message": "name already exists"})
            self.repos.add(body["name"])
            return httpx.Response(201, json={
                "full_name": f"ada/{body['name']}", "default_branch": "main",
                "html_url": f"https://github.com/ada/{body['name']}",
            })
        if path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "c0"}})
        if path.endswith("/git/commits/c0"):
            return httpx.Response(200, json={"tree": {"sha": "t0"}})
        if path.endswith("/git/blobs"):
            sha = f"b{len(self.blobs)}"
            self.blobs[sha] = base64.b64decode(body["content"])
            return httpx.Response(201, json={"sha": sha})
        if path.endswith("/git/trees"):
            return httpx.Response(201, json={"sha": "t1"})
        if path.endswith("/git/commits"):
            return httpx.Response(201, json={"sha": "c1"})
        if path.endswith("/git/refs/heads/main") and method == "PATCH":
            return httpx.Response(200, json={"object": {"sha": body["sha"]}})
        return httpx.Response(404)

    def calls(self, suffix: str, method: str | None = None) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith(suffix) and (method is None or r.method == method)]


@pytest.fixture
def fake() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
async def client(session_factory, fake, monkeypatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(settings, "web_url", "http://web")
    registry = init_registry(event_bus.publish, sessionmaker=session_factory)
    hub = GitHub(
        session_factory, client_id="cid", client_secret="csecret", redirect_uri="http://api/api/github/callback",
        encryption_key=Fernet.generate_key().decode(), http=httpx.AsyncClient(transport=httpx.MockTransport(fake)),
    )
    app = create_app()
    app.dependency_overrides[github_routes.github] = lambda: hub
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await hub.close()
    await registry.close()


async def connect(client: AsyncClient, user) -> httpx.Response:
    r = await client.get("/api/github/connect", params={"next": "/room/1"}, headers=auth(user))
    assert r.status_code == 200
    url = urlparse(r.json()["url"])
    query = parse_qs(url.query)
    assert (url.netloc, query["scope"], query["client_id"]) == ("github.com", ["repo"], ["cid"])
    return await client.get("/api/github/callback", params={"state": query["state"][0], "code": "good"})


async def test_connect_stores_the_token_encrypted(client, session_factory):
    user = uuid4()
    assert (await client.get("/api/github/status", headers=auth(user))).json() == {
        "configured": True, "connected": False, "login": None,
    }
    r = await connect(client, user)
    assert r.status_code == 303
    assert r.headers["location"] == "http://web/room/1?github=connected"
    async with session_factory() as session:
        row = await session.scalar(select(GithubToken).where(GithubToken.user_id == user))
    assert row is not None and TOKEN.encode() not in row.token_encrypted
    assert (await client.get("/api/github/status", headers=auth(user))).json()["login"] == "ada"


async def test_callback_rejects_unknown_or_reused_state_and_bad_codes(client):
    user = uuid4()
    r = await client.get("/api/github/callback", params={"state": "made-up", "code": "good"})
    assert r.headers["location"].startswith("http://web/profile?github=error")

    r = await client.get("/api/github/connect", headers=auth(user))
    state = parse_qs(urlparse(r.json()["url"]).query)["state"][0]
    r = await client.get("/api/github/callback", params={"state": state, "code": "bad"})
    assert "github=error" in r.headers["location"]
    r = await client.get("/api/github/callback", params={"state": state, "code": "good"})  # single use
    assert "expired" in r.headers["location"]


async def test_export_creates_a_repo_and_commits_the_room_files_without_force(client, fake):
    owner = uuid4()
    room = await new_room(client, owner)
    r = await client.post(f"/api/rooms/{room}/export", json={"repo_name": "my-app"}, headers=auth(owner))
    assert r.status_code == 409  # not connected yet

    await connect(client, owner)
    r = await client.post(f"/api/rooms/{room}/export", json={"repo_name": "my-app", "private": False},
                          headers=auth(owner))
    assert r.status_code == 200, r.text
    assert r.json()["url"] == "https://github.com/ada/my-app"

    created = json.loads(fake.calls("/user/repos")[0].content)
    assert (created["private"], created["auto_init"]) == (False, True)
    files = await client.get(f"/api/rooms/{room}/files", headers=auth(owner))
    assert len(fake.blobs) == len(files.json()) == r.json()["files"]
    assert any(b'"name": "mux-app"' in blob for blob in fake.blobs.values())  # the template's package.json
    tree = json.loads(fake.calls("/git/trees")[0].content)
    assert tree["base_tree"] == "t0" and "package.json" in {item["path"] for item in tree["tree"]}
    commit = json.loads(fake.calls("/git/commits", "POST")[0].content)
    assert commit["parents"] == ["c0"]
    update = json.loads(fake.calls("/git/refs/heads/main", "PATCH")[0].content)
    assert update == {"sha": "c1"}  # a fast-forward, never force

    r = await client.post(f"/api/rooms/{room}/export", json={"repo_name": "taken"}, headers=auth(owner))
    assert r.status_code == 409 and "already" in r.json()["detail"]


async def test_export_needs_editor_and_a_valid_name(client):
    owner, stranger = uuid4(), uuid4()
    room = await new_room(client, owner)
    r = await client.post(f"/api/rooms/{room}/export", json={"repo_name": "x"}, headers=auth(stranger))
    assert r.status_code == 404
    r = await client.post(f"/api/rooms/{room}/export", json={"repo_name": "bad name/"}, headers=auth(owner))
    assert r.status_code == 422
