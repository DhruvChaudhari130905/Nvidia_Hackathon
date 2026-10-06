"""Room WebSocket at /ws/rooms/{room_id}?token=<Supabase JWT>&since=<seq>.

Server to client: every stored event after `since` (all of them for since=0), then live events, each an
EventEnvelope. Presence envelopes are never stored and carry the last stored seq. Control replies have no seq:
{"type": "pong"} and {"type": "error", "detail": "..."}.
Client to server: {"type": "tab", "tab": "code"}, {"type": "typing", "typing": true}, {"type": "ping"}.
"""

import asyncio
import contextlib
import json
import logging
from typing import Any, Protocol, get_args
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, WebSocketException, status

from mux.api.deps import CurrentUser, user_from_token
from mux.events import log
from mux.events.bus import EventBus, event_bus
from mux.events.models import Tab
from mux.rooms.actor import RoomActor
from mux.rooms.registry import get_registry

logger = logging.getLogger(__name__)

router = APIRouter()

LIVE_BACKLOG = 1000  # live messages a client may fall behind by before it is dropped
TABS: tuple[str, ...] = get_args(Tab)


class ClientSocket(Protocol):
    """What `serve` needs from a connection. FastAPI's WebSocket has it; tests use a fake."""

    async def send_text(self, data: str) -> None: ...

    async def receive_text(self) -> str: ...


class Outbox:
    """One connection's queue of outgoing text. The bus writes here, so a slow client never holds up the room;
    one writer task sends the queue in order."""

    def __init__(self, limit: int) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.limit = limit
        self.overflow = asyncio.Event()

    def put(self, text: str) -> None:
        self.queue.put_nowait(text)

    async def send_text(self, data: str) -> None:
        """The bus's send. Raising makes the bus drop this connection; the client reconnects with ?since."""
        if self.queue.qsize() >= self.limit:
            self.overflow.set()
            raise ConnectionError("the client fell too far behind")
        self.queue.put_nowait(data)


@router.websocket("/rooms/{room_id}")
async def room_socket(
    websocket: WebSocket, room_id: UUID, since: int = Query(0, ge=0), token: str | None = Query(None)
) -> None:
    """The token is a query parameter because browsers cannot set headers on a WebSocket.
    Auth and access are checked before the connection is accepted."""
    user = user_from_token(token)
    if user is None:
        raise WebSocketException(status.WS_1008_POLICY_VIOLATION, "not signed in")
    actor = await get_registry().get(room_id)
    if actor is None or actor.role_of(user.id) is None:
        raise WebSocketException(status.WS_1008_POLICY_VIOLATION, "room not found")
    await websocket.accept()
    if await serve(actor, websocket, user, since):
        with contextlib.suppress(Exception):
            await websocket.close(status.WS_1013_TRY_AGAIN_LATER, "fell behind; reconnect with ?since")


async def serve(
    actor: RoomActor, socket: ClientSocket, user: CurrentUser, since: int, *, bus: EventBus = event_bus
) -> bool:
    """Run one connection until the client leaves. True if it was dropped for falling behind.

    The stored events are read and the outbox subscribed while the emitter holds new events back,
    so the client gets every event after `since` exactly once, in seq order."""
    async with actor.emitter.hold():
        async with actor.emitter.sessionmaker() as s:
            missed = await log.read_since(actor.room_id, since, session=s)
        outbox = Outbox(len(missed) + LIVE_BACKLOG)
        for event in missed:
            outbox.put(event.model_dump_json())
        bus.connect(actor.room_id, outbox)
    try:
        await actor.connect(user.id, user.name)
        try:
            await _pump(actor, socket, user.id, outbox)
        finally:
            await actor.disconnect(user.id)
    finally:
        bus.disconnect(actor.room_id, outbox)
    return outbox.overflow.is_set()


async def _pump(actor: RoomActor, socket: ClientSocket, user_id: UUID, outbox: Outbox) -> None:
    """Send the outbox and read client messages at once. Stops when the client leaves, a send fails,
    or the outbox overflows."""
    writer = asyncio.create_task(_write(outbox, socket))
    reader = asyncio.create_task(_read(actor, socket, user_id, outbox))
    overflow = asyncio.create_task(outbox.overflow.wait())
    tasks = (writer, reader, overflow)
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
    if isinstance(results[1], Exception):
        logger.error("WebSocket reader failed in room %s", actor.room_id, exc_info=results[1])


async def _write(outbox: Outbox, socket: ClientSocket) -> None:
    while True:
        await socket.send_text(await outbox.queue.get())


async def _read(actor: RoomActor, socket: ClientSocket, user_id: UUID, outbox: Outbox) -> None:
    """Handle client messages until the client disconnects. A bad message gets an error reply."""
    while True:
        try:
            text = await socket.receive_text()
        except WebSocketDisconnect:
            return
        try:
            await handle(actor, user_id, json.loads(text), outbox)
        except ValueError as e:  # bad JSON is a ValueError too
            outbox.put(json.dumps({"type": "error", "detail": str(e)}))


async def handle(actor: RoomActor, user_id: UUID, message: Any, outbox: Outbox) -> None:
    """One client message. Raises ValueError for a message the server does not understand."""
    kind = message.get("type") if isinstance(message, dict) else None
    if kind == "ping":
        outbox.put(json.dumps({"type": "pong"}))
    elif kind == "tab":
        if message.get("tab") not in TABS:
            raise ValueError(f"tab must be one of {', '.join(TABS)}")
        await actor.set_tab(user_id, message["tab"])
    elif kind == "typing":
        if not isinstance(message.get("typing"), bool):
            raise ValueError("typing must be true or false")
        await actor.set_typing(user_id, message["typing"])
    else:
        raise ValueError(f"unknown message type {kind!r}")
