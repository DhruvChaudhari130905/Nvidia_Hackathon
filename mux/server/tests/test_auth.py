"""Supabase token checks (legacy secret and signing keys), the WebSocket's token handling, and request limits."""

import time
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from mux.api.ws import token_from_subprotocols
from mux.auth import supabase
from mux.auth.supabase import verify_supabase_token
from mux.config import settings
from mux.main import create_app
from tests.test_api import SECRET, auth, client, jwt_secret, new_room  # noqa: F401  (fixtures)

PROJECT = "https://abc.supabase.co"


def claims(**overrides):
    base = {"sub": str(uuid4()), "aud": "authenticated", "exp": int(time.time()) + 600}
    return {k: v for k, v in {**base, **overrides}.items() if v is not None}


@pytest.fixture
def audience(monkeypatch):
    """Supabase's defaults: the audience is checked."""
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")


def test_legacy_secret_tokens(audience):
    assert verify_supabase_token(jwt.encode(claims(), SECRET, algorithm="HS256")) is not None
    assert verify_supabase_token(jwt.encode(claims(), "wrong-secret-that-is-32-bytes-long", algorithm="HS256")) is None
    assert verify_supabase_token(jwt.encode(claims(aud="anon"), SECRET, algorithm="HS256")) is None
    assert verify_supabase_token(jwt.encode(claims(exp=int(time.time()) - 5), SECRET, algorithm="HS256")) is None
    assert verify_supabase_token(jwt.encode(claims(sub=None), SECRET, algorithm="HS256")) is None
    assert verify_supabase_token(jwt.encode(claims(exp=None), SECRET, algorithm="HS256")) is None
    assert verify_supabase_token("not-a-jwt") is None


def test_unsigned_and_unknown_algorithms_are_rejected(audience):
    assert verify_supabase_token(jwt.encode(claims(), "", algorithm="none")) is None
    assert verify_supabase_token(jwt.encode(claims(), SECRET * 2, algorithm="HS512")) is None


def test_signing_key_tokens(audience, monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    fetched: list[str] = []

    def jwks(url):
        fetched.append(url)
        return SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()))

    monkeypatch.setattr(supabase, "_jwks", jwks)
    issuer = f"{PROJECT}/auth/v1"
    signed = jwt.encode(claims(iss=issuer), key, algorithm="ES256")
    assert verify_supabase_token(signed) is None  # no SUPABASE_URL: no keys to check against

    monkeypatch.setattr(settings, "supabase_url", PROJECT)
    assert verify_supabase_token(signed) is not None
    assert fetched[-1] == f"{PROJECT}/auth/v1/.well-known/jwks.json"
    assert verify_supabase_token(jwt.encode(claims(iss="https://evil.example/auth/v1"), key, algorithm="ES256")) is None
    other = ec.generate_private_key(ec.SECP256R1())
    assert verify_supabase_token(jwt.encode(claims(iss=issuer), other, algorithm="ES256")) is None


def test_unverified_tokens_need_debug_too(monkeypatch):
    forged = jwt.encode(claims(), "anything-anything-anything-anything", algorithm="HS256")
    monkeypatch.setattr(settings, "allow_unverified_tokens", True)
    assert verify_supabase_token(forged) is None  # DEBUG is off
    monkeypatch.setattr(settings, "debug", True)
    assert verify_supabase_token(forged) is not None


def test_websocket_token_comes_from_the_subprotocol():
    assert token_from_subprotocols(["mux", "a.b.c"]) == "a.b.c"
    assert token_from_subprotocols(["a.b.c"]) is None
    assert token_from_subprotocols(["mux"]) is None
    assert token_from_subprotocols([]) is None


def test_websocket_without_a_token_is_refused():
    with TestClient(create_app()) as c, pytest.raises(WebSocketDisconnect) as refused:
        with c.websocket_connect(f"/ws/rooms/{uuid4()}?since=0", subprotocols=["mux"]):
            pass
    assert refused.value.code == 1008


async def test_request_limits(client):  # noqa: F811
    owner = uuid4()
    r = await client.post("/api/rooms", json={"title": "r", "description": "x" * 5000}, headers=auth(owner))
    assert r.status_code == 422
    room = await new_room(client, owner)
    r = await client.put(f"/api/rooms/{room}/plan", json={"items": [{"id": f"t{n}", "title": "x"} for n in range(101)]},
                         headers=auth(owner))
    assert r.status_code == 422
    r = await client.post(f"/api/rooms/{room}/plan/items", json={"id": "t1", "title": "x", "notes": "n" * 2001},
                          headers=auth(owner))
    assert r.status_code == 400


async def test_people_change_only_some_task_fields(client):  # noqa: F811
    owner = uuid4()
    room = await new_room(client, owner)
    assert (await client.post(f"/api/rooms/{room}/plan/items", json={"id": "t1", "title": "x"},
                              headers=auth(owner))).status_code == 204
    patch = lambda body: client.patch(f"/api/rooms/{room}/plan/items/t1", json=body, headers=auth(owner))  # noqa: E731
    assert (await patch({"status": "done"})).status_code == 422
    assert (await patch({"merged_notes": ["sneaky"]})).status_code == 422
    assert (await patch({"id": "t9"})).status_code == 422
    assert (await patch({})).status_code == 400
    assert (await patch({"title": None})).status_code == 400
    assert (await patch({"status": "todo", "notes": "retry with less scope"})).status_code == 204
