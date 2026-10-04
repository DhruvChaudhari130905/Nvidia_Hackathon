"""Room WebSocket. Streams events from ?since=seq and carries ephemeral presence (avatars, typing, active tab)."""

from __future__ import annotations

import json
import logging
from typing import Optional

from uuid import uuid4

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, WebSocketException, status

from mux.auth.supabase import User, verify_supabase_token
from mux.events.bus import event_bus
from mux.events.models import BaseEvent, EventType
from mux.rooms.registry import get_registry
from mux.rooms.actor import RoomActor, ROOM_ID_PATTERN

logger = logging.getLogger(__name__)

router = APIRouter()


# Map backend event types to frontend-compatible aliases
EVENT_TYPE_ALIASES = {
    EventType.USER_JOINED: EventType.PRESENCE_JOIN,
    EventType.USER_LEFT: EventType.PRESENCE_LEAVE,
    EventType.USER_TYPING: EventType.PRESENCE_TYPING,
    EventType.USER_PRESENCE_CHANGED: EventType.PRESENCE_TAB,
    EventType.PLAN_ITEM_ADDED: EventType.PLAN_ITEM_ADDED_ALIAS,
    EventType.PLAN_ITEM_UPDATED: EventType.PLAN_ITEM_UPDATED_ALIAS,
    EventType.COMMAND_APPROVE_PLAN: EventType.PLAN_APPROVED,
    EventType.USER_MESSAGE_SENT: EventType.MESSAGE_POSTED,
    EventType.COMMAND_VOTE: EventType.CONFLICT_VOTE,
    EventType.COMMAND_OVERRIDE: EventType.CONFLICT_OVERRIDE,
    EventType.COMMAND_ANSWER_QUESTION: EventType.QUESTION_ANSWER,
    EventType.PLAN_ITEM_COMPLETED: EventType.TASK_FINISHED,
    EventType.FILE_CREATED: EventType.FILE_CHANGED,
    EventType.FILE_UPDATED: EventType.FILE_CHANGED,
    EventType.COMMAND_REWIND: EventType.ROOM_REWOUND,
    EventType.BUDGET_EXCEEDED: EventType.BUDGET_UPDATED,
    EventType.CONFLICT_DETECTED: EventType.CONFLICT_OPENED,
    EventType.CONFLICT_RESOLVED: EventType.CONFLICT_CLOSED,
    EventType.QUESTION_ASKED: EventType.QUESTION_OPENED,
    EventType.QUESTION_ANSWERED: EventType.QUESTION_ANSWER,
    EventType.CHECKPOINT_CREATED: EventType.CHECKPOINT_CREATED,  # Same
    EventType.SITTING_ENDED: EventType.SITTING_ENDED,  # Same
}


# =============================================================================
# WebSocket Authentication
# =============================================================================

async def authenticate_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
) -> User:
    """
    Authenticate WebSocket connection via JWT token.
    Token can be passed as query parameter or Authorization header.
    """
    # Try query param first, then header
    auth_token = token
    if not auth_token:
        auth_header = websocket.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header[7:]

    if not auth_token:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing authentication token"
        )

    # Same verification as the REST API (handles Supabase's aud claim)
    payload = verify_supabase_token(auth_token)
    if payload is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid or expired token"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Token missing user ID"
        )

    return User(
        id=user_id,
        email=payload.get("email"),
        role=payload.get("role", "authenticated"),
    )


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/rooms/{room_id}")
async def room_websocket(
    websocket: WebSocket,
    room_id: str,
    since: Optional[int] = Query(None, description="Event sequence to replay from"),
    user: User = Depends(authenticate_websocket),
):
    """
    WebSocket endpoint for real-time room events and presence.

    Query Parameters:
    - since: Event sequence number to replay from (optional)

    Message Types (client -> server):
    - {"type": "presence", "status": "online|away|offline", "tab": "editor|terminal|...", "cursor": {...}, "typing": true|false}
    - {"type": "ping"} (responds with pong)

    Event Types (server -> client):
    - All domain events (plan, files, budget, sitting, presence, etc.) plus frontend aliases
    - {"type": "presence_update", "user_id": "...", "status": "...", "tab": "...", "cursor": {...}, "typing": true|false}
    - {"type": "pong"} (response to ping)
    - {"type": "error", "message": "..."}
    """
    # Look up (or rehydrate) the room; WebSockets never create rooms
    actor = None
    if ROOM_ID_PATTERN.match(room_id):
        actor = await get_registry().get_room_or_rehydrate(room_id)
    if actor is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Room not found")
    if actor.role_of(user.id) is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="No access to this room")

    await websocket.accept()

    try:
        # Replay events from sequence if requested (before live events start flowing)
        if since is not None and since > 0:
            events = await actor.event_log.read_from(since, limit=1000)
            for event in events:
                await websocket.send_text(event.model_dump_json())

        # Register with event bus for real-time broadcasts
        event_bus.connect(room_id, websocket)

        # Join the room (records presence + sitting activity; the actor broadcasts user_joined)
        await actor.user_join(user_id=user.id)

        # Main message loop
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                if not isinstance(message, dict):
                    raise ValueError("Message must be a JSON object")
                await handle_client_message(actor, message, user.id, websocket, room_id)
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await send_error(websocket, "Invalid JSON")
            except ValueError as e:
                await send_error(websocket, str(e))
            except Exception as e:
                logger.exception(f"Error handling WebSocket message: {e}")
                await send_error(websocket, "Internal error")
    except WebSocketDisconnect:
        pass

    finally:
        # Cleanup (the actor broadcasts user_left)
        event_bus.disconnect(room_id, websocket)
        await actor.user_leave(user.id)


# =============================================================================
# Message Handlers
# =============================================================================

async def handle_client_message(
    actor: RoomActor,
    message: dict,
    user_id: str,
    websocket: WebSocket,
    room_id: str,
):
    """Handle incoming client messages for presence updates."""
    msg_type = message.get("type")

    if msg_type == "presence":
        await handle_presence_update(actor, message, user_id, room_id)
    elif msg_type == "ping":
        await websocket.send_text(json.dumps({"type": "pong"}))
    else:
        await send_error(websocket, f"Unknown message type: {msg_type}")


async def handle_presence_update(
    actor: RoomActor,
    message: dict,
    user_id: str,
    room_id: str,
):
    """Handle presence update from client."""
    # Typing indicator
    if "typing" in message:
        await actor.set_typing(user_id, message["typing"])

    # Active tab
    if "tab" in message:
        await actor.set_active_tab(user_id, message["tab"])

    # Cursor position
    if "cursor" in message:
        await actor.set_cursor(user_id, message["cursor"])

    # Presence status
    if "status" in message:
        await actor.set_presence_status(user_id, message["status"])

    # Broadcast the full presence snapshot (typing/status changes are also
    # broadcast as events by the actor)
    presence = await actor.presence.get(user_id)
    if presence:
        await event_bus.publish_json(room_id, {
            "type": "presence_update",
            "user_id": user_id,
            "user_name": presence.user_name,
            "avatar_url": presence.avatar_url,
            "status": presence.status,
            "tab": presence.active_tab,
            "cursor": presence.cursor_position,
            "typing": presence.typing,
        })


async def send_error(websocket: WebSocket, message: str):
    """Send error message to client."""
    try:
        await websocket.send_text(json.dumps({"type": "error", "message": message}))
    except Exception:
        pass


async def emit_event_with_alias(room_id: str, event: BaseEvent) -> None:
    """
    Emit an event and its frontend-compatible alias (if any) to all WebSocket connections in a room.
    """
    # Publish the original event
    await event_bus.publish(room_id, event)

    # Also publish the alias with the full payload. (Rebuilding it as a BaseEvent
    # dropped every subclass field, so e.g. message.posted arrived without content.)
    alias_type = EVENT_TYPE_ALIASES.get(event.type)
    if alias_type and alias_type != event.type:
        payload = event.model_dump(mode="json")
        payload["type"] = alias_type.value
        payload["id"] = str(uuid4())  # New UUID for alias event
        await event_bus.publish_json(room_id, payload)


# =============================================================================
# Health check endpoint for load balancers
# =============================================================================

@router.get("/health")
async def ws_health():
    """WebSocket health check."""
    return {"status": "healthy", "connections": event_bus.connection_count()}