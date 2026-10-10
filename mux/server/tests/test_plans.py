"""Plans: the Free room limit, and upgrading raising room budgets right away (no payment step yet)."""

import mux.rooms.registry as room_registry
from tests.test_api import auth, client, create_room, registry_call  # noqa: F401  (client is a fixture)


def budget(c, rid):
    room = c.get(f"/rooms/{rid}", headers=auth("alice")).json()
    return room["budget_tokens_cap"], room["budget_runs_cap"]


def test_new_users_are_on_free(client):
    r = client.get("/me/plan", headers=auth("alice"))
    assert r.status_code == 200
    assert r.json() == {"plan": "free", "label": "Free Developer", "room_limit": 3, "token_cap": 1_000_000,
                        "run_cap": 100, "rooms_owned": 0}


def test_free_plan_stops_at_three_owned_rooms(client):
    for _ in range(3):
        create_room(client)
    r = client.post("/rooms", json={"description": "one too many"}, headers=auth("alice"))
    assert r.status_code == 403 and "Upgrade" in r.json()["detail"]
    # The limit is per owner: someone else can still create rooms
    create_room(client, owner="bob")


def test_upgrading_raises_existing_rooms_and_lifts_the_limit(client):
    rooms = [create_room(client) for _ in range(3)]
    assert budget(client, rooms[0]) == (1_000_000, 100)

    r = client.put("/me/plan", json={"plan": "pro"}, headers=auth("alice"))
    assert r.status_code == 200 and r.json()["plan"] == "pro" and r.json()["room_limit"] is None
    assert r.json()["rooms_owned"] == 3
    assert all(budget(client, rid) == (5_000_000, 500) for rid in rooms)

    fourth = create_room(client)
    assert budget(client, fourth) == (5_000_000, 500)

    client.put("/me/plan", json={"plan": "enterprise"}, headers=auth("alice"))
    assert budget(client, fourth) == (20_000_000, 2_000)


def test_plan_survives_a_room_being_rebuilt(client):
    rid = create_room(client)
    client.put("/me/plan", json={"plan": "pro"}, headers=auth("alice"))
    registry_call(client, room_registry.get_registry().stop_room, rid)
    assert budget(client, rid) == (5_000_000, 500)


def test_downgrading_keeps_existing_rooms_but_new_rooms_are_free_sized(client):
    client.put("/me/plan", json={"plan": "pro"}, headers=auth("alice"))
    rid = create_room(client)
    client.put("/me/plan", json={"plan": "free"}, headers=auth("alice"))
    assert budget(client, rid) == (5_000_000, 500)
    assert budget(client, create_room(client)) == (1_000_000, 100)


def test_unknown_plans_are_rejected(client):
    assert client.put("/me/plan", json={"plan": "platinum"}, headers=auth("alice")).status_code == 422
    assert client.get("/me/plan").status_code in (401, 403)
