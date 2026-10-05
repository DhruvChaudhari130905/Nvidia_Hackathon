
"""EventBus: routing by room, envelope JSON, dropping dead connections."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from mux.events.bus import EventBus
from mux.events.models import EventEnvelope


class FakeSocket:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[str] = []
        self.fail = fail

    async def send_text(self, data: str) -> None:
        if self.fail:
            raise ConnectionError("gone")
        self.sent.append(data)


def envelope(room_id, seq=1):
    return EventEnvelope(seq=seq, type="plan.approved", ts=datetime.now(UTC), room_id=room_id, actor="u1", payload={})


async def test_publish_goes_to_the_events_room_only():
    bus, room_a, room_b = EventBus(), uuid4(), uuid4()
    in_a, in_b = FakeSocket(), FakeSocket()
    bus.connect(room_a, in_a)
    bus.connect(room_b, in_b)
    await bus.publish(envelope(room_a))
    assert len(in_a.sent) == 1
    assert in_b.sent == []


async def test_sent_json_is_the_envelope():
    bus, room = EventBus(), uuid4()
    socket = FakeSocket()
    bus.connect(room, socket)
    await bus.publish(envelope(room, seq=7))
    sent = json.loads(socket.sent[0])
    assert set(sent) == {"seq", "type", "ts", "room_id", "actor", "payload"}
    assert (sent["seq"], sent["room_id"]) == (7, str(room))


async def test_dead_socket_is_dropped_and_others_still_get_the_event():
    bus, room = EventBus(), uuid4()
    dead, alive = FakeSocket(fail=True), FakeSocket()
    bus.connect(room, dead)
    bus.connect(room, alive)
    await bus.publish(envelope(room))
    assert len(alive.sent) == 1
    assert bus.connection_count(room) == 1


def test_disconnect_forgets_empty_rooms():
    bus, room = EventBus(), uuid4()
    socket = FakeSocket()
    bus.connect(room, socket)
    bus.disconnect(room, socket)
    bus.disconnect(room, socket)  # twice is harmless
    assert bus.connection_count() == 0