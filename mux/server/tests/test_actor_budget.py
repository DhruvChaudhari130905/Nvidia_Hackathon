"""Actor budget: usage is stored, a cap pauses the room, raising it resumes, and reopening keeps it."""

from uuid import uuid4

import pytest

from mux.rooms.actor import RoomActor
from mux.rooms.budget import Budget


@pytest.fixture
def published():
    return []


@pytest.fixture
def publish(published):
    async def _publish(event):
        published.append(event)
    return _publish


async def new_room(session_factory, publish):
    owner = uuid4()
    return await RoomActor.create(owner, "r", publish, template={}, sessionmaker=session_factory), owner


def after_create(published):
    return [e.type for e in published[2:]]


async def test_charge_is_stored_and_survives_reopen(session_factory, publish, published):
    actor, _ = await new_room(session_factory, publish)
    await actor.charge(tokens=1200, runs=1)
    assert after_create(published) == ["budget.updated"]
    assert published[-1].payload == {"tokens_used": 1200, "runs_used": 1, "tokens_cap": 2_000_000, "runs_cap": 100}
    await actor.charge(tokens=300)
    reopened = await RoomActor.open(actor.room_id, publish, sessionmaker=session_factory)
    assert reopened is not None
    assert reopened.budget == actor.budget == Budget(tokens_used=1500, runs_used=1)


async def test_zero_and_negative_usage(session_factory, publish, published):
    actor, _ = await new_room(session_factory, publish)
    await actor.charge()
    assert after_create(published) == []
    with pytest.raises(ValueError):
        await actor.charge(tokens=-1)


async def test_cap_pauses_and_raising_it_resumes(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish)
    await actor.set_budget_caps(1000, 10, str(owner))
    await actor.charge(tokens=1500)
    assert actor.paused
    await actor.charge(tokens=10)  # already spent, so it still counts; no second pause
    assert actor.budget.tokens_used == 1510
    await actor.set_budget_caps(5000, 10, str(owner))
    assert not actor.paused
    assert after_create(published) == [
        "budget.updated", "budget.updated", "room.paused", "budget.updated", "budget.updated", "room.resumed",
    ]
    assert next(e for e in published if e.type == "room.paused").payload == {"reason": "tokens"}


async def test_lower_caps_pause_and_reopen_stays_paused(session_factory, publish):
    actor, owner = await new_room(session_factory, publish)
    await actor.charge(runs=5)
    await actor.set_budget_caps(2_000_000, 5, str(owner))
    assert actor.budget.over == "runs"
    reopened = await RoomActor.open(actor.room_id, publish, sessionmaker=session_factory)
    assert reopened is not None
    assert reopened.paused


async def test_caps_must_be_positive(session_factory, publish):
    actor, owner = await new_room(session_factory, publish)
    with pytest.raises(ValueError):
        await actor.set_budget_caps(0, 10, str(owner))
