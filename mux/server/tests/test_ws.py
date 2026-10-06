"""Room WebSocket: stored events after ?since, then live ones with no gap or duplicate; presence; client messages."""

import asyncio
import json
from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect

from mux.api import ws
from mux.api.deps import CurrentUser
from mux.api.ws import serve
from mux.events.bus import EventBus
from mux.rooms.actor import RoomActor


class FakeSocket:
    """A client: `incoming` is what it sends (None hangs up), `sent` what it received."""

    def __init__(self) -> None:
        self.incoming: asyncio.Queue[str | None] = asyncio.Queue()
        self.sent: list[dict] = []

    async def send_text(self, data: str) -> None:
        self.sent.append(json.loads(data))

    async def receive_text(self) -> str:
        text = await self.incoming.get()
        if text is None:
            raise WebSocketDisconnect()
        return text

    def types(self) -> list[str]:
        return [m["type"] for m in self.sent]

    def stored(self) -> list[int]:
        """Seqs of the stored events received (presence and control replies left out)."""
        return [m["seq"] for m in self.sent if "seq" in m and not m["type"].startswith("presence.")]


class StuckSocket(FakeSocket):
    """A client that never reads what it is sent."""

    async def send_text(self, data: str) -> None:
        await asyncio.Event().wait()


async def until(condition, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


@pytest.fixture
def bus():
    return EventBus()


async def new_room(session_factory, bus):
    owner = uuid4()
    actor = await RoomActor.create(owner, "r", bus.publish, template={}, sessionmaker=session_factory)
    return actor, CurrentUser(owner, "Ada")


async def test_since_replays_the_missed_events_then_live_ones(session_factory, bus):
    actor, user = await new_room(session_factory, bus)
    await actor.post_message(user.id, "one")  # seq 3
    socket = FakeSocket()
    task = asyncio.create_task(serve(actor, socket, user, 2, bus=bus))
    await until(lambda: "presence.join" in socket.types())
    await actor.post_message(user.id, "two")
    await until(lambda: len(socket.stored()) == 2)
    assert socket.stored() == [3, 4]
    assert socket.types()[:2] == ["message.posted", "presence.join"]
    assert socket.sent[1]["payload"]["name"] == "Ada"

    await socket.incoming.put(None)
    assert await task is False
    assert bus.connection_count(actor.room_id) == 0
    assert user.id not in actor.presence


async def test_since_zero_replays_the_whole_room(session_factory, bus):
    actor, user = await new_room(session_factory, bus)
    socket = FakeSocket()
    task = asyncio.create_task(serve(actor, socket, user, 0, bus=bus))
    await until(lambda: "presence.join" in socket.types())
    assert socket.types()[:2] == ["room.created", "checkpoint.created"]
    await socket.incoming.put(None)
    await task


async def test_events_during_the_replay_arrive_once_and_in_order(session_factory, bus):
    actor, user = await new_room(session_factory, bus)
    sockets = [FakeSocket() for _ in range(5)]
    tasks = [asyncio.create_task(serve(actor, s, user, 0, bus=bus)) for s in sockets]
    for i in range(5):
        await actor.post_message(user.id, str(i))
    for s in sockets:
        await until(lambda s=s: len(s.stored()) == 7)
        assert s.stored() == [1, 2, 3, 4, 5, 6, 7]
    for s in sockets:
        await s.incoming.put(None)
    await asyncio.gather(*tasks)


async def test_client_messages(session_factory, bus):
    actor, user = await new_room(session_factory, bus)
    socket = FakeSocket()
    task = asyncio.create_task(serve(actor, socket, user, 2, bus=bus))
    for message in ({"type": "tab", "tab": "code"}, {"type": "typing", "typing": True}, {"type": "ping"}):
        await socket.incoming.put(json.dumps(message))
    for bad in ("not json", json.dumps({"type": "tab", "tab": "nope"}), json.dumps({"type": "dance"}), "[]"):
        await socket.incoming.put(bad)
    await until(lambda: socket.types().count("error") == 4)
    assert socket.types()[:4] == ["presence.join", "presence.tab", "presence.typing", "pong"]
    assert actor.presence[user.id].tab == "code"
    await socket.incoming.put(None)
    await task


async def test_a_client_that_falls_behind_is_dropped(session_factory, bus, monkeypatch):
    monkeypatch.setattr(ws, "LIVE_BACKLOG", 1)
    actor, user = await new_room(session_factory, bus)
    task = asyncio.create_task(serve(actor, StuckSocket(), user, 2, bus=bus))
    await until(lambda: user.id in actor.presence)
    for i in range(3):
        await actor.post_message(user.id, str(i))
    async with asyncio.timeout(2):
        assert await task is True
    assert bus.connection_count(actor.room_id) == 0
    assert user.id not in actor.presence
