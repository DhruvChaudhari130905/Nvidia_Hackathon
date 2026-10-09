"""A room's MCP servers (mux/mcp): everyone in the room can see them, only the owner changes them."""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

import mux.mcp.catalog as mcp_catalog
import mux.mcp.client as mcp_client
import mux.mcp.config as mcp_config
from mux.api.deps import User, get_room_actor_dep, require_owner, require_viewer
from mux.mcp.catalog import room_mcp_view
from mux.mcp.client import ToolInfo, describe_error
from mux.mcp.config import ServerSpec
from mux.mcp.names import header_problem
from mux.secrets import SecretsUnavailable, decrypt_values, encrypt_values
from mux.urls import UrlNotAllowed, check_url_async
from mux.rooms.actor import RoomActor

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_ROOM_SERVERS = 10
SERVER_NAME = r"^[a-z0-9_-]{1,32}$"


class ToolSettingModel(BaseModel):
    enabled: bool = True
    mode: Literal["auto", "ask"] = "auto"


def _checked_headers(headers: Optional[dict[str, str]]) -> Optional[dict[str, str]]:
    for name, value in (headers or {}).items():
        if problem := header_problem(name, value):
            raise ValueError(problem)
    return headers


class ServerAddRequest(BaseModel):
    name: str = Field(..., pattern=SERVER_NAME)
    url: str = Field(..., min_length=8, max_length=2000)
    headers: dict[str, str] = Field(default_factory=dict, description="e.g. {\"Authorization\": \"Bearer ...\"}")

    _headers_ok = field_validator("headers")(_checked_headers)


class ServerUpdateRequest(BaseModel):
    headers: Optional[dict[str, str]] = Field(None, description="Replaces all saved headers")
    settings: Optional[dict[str, ToolSettingModel]] = None

    _headers_ok = field_validator("headers")(_checked_headers)


class AdminUpdateRequest(BaseModel):
    enabled: bool
    settings: Optional[dict[str, ToolSettingModel]] = None


def _settings(settings: Optional[dict[str, ToolSettingModel]], tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Only settings for tools the server has."""
    known = {t["name"] for t in tools}
    return {name: s.model_dump() for name, s in (settings or {}).items() if name in known}


def _encrypt(headers: dict[str, str]) -> dict[str, str]:
    try:
        return encrypt_values(headers)
    except SecretsUnavailable as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


async def _tools(spec: ServerSpec, *, room_server: bool) -> list[dict[str, Any]]:
    """Connect and list the server's tools: 400 for a refused URL, 502 if it can't be reached."""
    if room_server and spec.url:
        try:
            await check_url_async(spec.url)
        except UrlNotAllowed as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    try:
        return [t.to_dict() for t in await mcp_client.fetch_tools(spec)]
    except Exception as e:
        reason = describe_error(e, secrets=[*spec.headers.values(), *spec.env.values()], room_server=room_server)
        logger.warning(f"MCP server {spec.name}: could not list tools: {reason}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not connect to {spec.name}: {reason}")


def _room_server(actor: RoomActor, name: str) -> dict[str, Any]:
    server = actor.mcp_servers.get(name)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No MCP server named {name} in this room")
    return server


@router.get("/{room_id}/mcp")
async def get_mcp(room_id: str, current_user: User = Depends(require_viewer),
                  actor: RoomActor = Depends(get_room_actor_dep)) -> dict[str, Any]:
    return room_mcp_view(actor)


@router.post("/{room_id}/mcp/servers")
async def add_server(room_id: str, request: ServerAddRequest, current_user: User = Depends(require_owner),
                     actor: RoomActor = Depends(get_room_actor_dep)) -> dict[str, Any]:
    if request.name in actor.mcp_servers or request.name in mcp_config.admin_servers():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"There's already a server named {request.name}")
    if len(actor.mcp_servers) >= MAX_ROOM_SERVERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"A room can have at most {MAX_ROOM_SERVERS} MCP servers")
    headers = _encrypt(request.headers)  # before connecting: no key, no point trying
    tools = await _tools(ServerSpec(request.name, url=request.url, headers=request.headers), room_server=True)
    await actor.save_mcp_server(request.name, request.url, headers, tools, {}, current_user.id)
    return room_mcp_view(actor)


@router.post("/{room_id}/mcp/servers/{name}/refresh")
async def refresh_server(room_id: str, name: str, current_user: User = Depends(require_owner),
                         actor: RoomActor = Depends(get_room_actor_dep)) -> dict[str, Any]:
    server = _room_server(actor, name)
    try:
        headers = decrypt_values(server["headers"])
    except SecretsUnavailable as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    tools = await _tools(ServerSpec(name, url=server["url"], headers=headers), room_server=True)
    known = {t["name"] for t in tools}
    settings = {tool: s for tool, s in server["settings"].items() if tool in known}
    await actor.save_mcp_server(name, server["url"], server["headers"], tools, settings, current_user.id)
    return room_mcp_view(actor)


@router.patch("/{room_id}/mcp/servers/{name}")
async def update_server(room_id: str, name: str, request: ServerUpdateRequest, current_user: User = Depends(require_owner),
                        actor: RoomActor = Depends(get_room_actor_dep)) -> dict[str, Any]:
    server = _room_server(actor, name)
    headers = _encrypt(request.headers) if request.headers is not None else server["headers"]
    settings = _settings(request.settings, server["tools"]) if request.settings is not None else server["settings"]
    await actor.save_mcp_server(name, server["url"], headers, server["tools"], settings, current_user.id)
    return room_mcp_view(actor)


@router.delete("/{room_id}/mcp/servers/{name}")
async def remove_server(room_id: str, name: str, current_user: User = Depends(require_owner),
                        actor: RoomActor = Depends(get_room_actor_dep)) -> dict[str, Any]:
    if not await actor.remove_mcp_server(name, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No MCP server named {name} in this room")
    return room_mcp_view(actor)


def _admin_spec(name: str) -> ServerSpec:
    spec = mcp_config.admin_servers().get(name)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No server-wide MCP server named {name}")
    return spec


@router.patch("/{room_id}/mcp/admin/{name}")
async def update_admin(room_id: str, name: str, request: AdminUpdateRequest, current_user: User = Depends(require_owner),
                       actor: RoomActor = Depends(get_room_actor_dep)) -> dict[str, Any]:
    _admin_spec(name)
    current = (actor.mcp_admin.get(name) or {}).get("settings") or {}
    # Tool lists of server-wide servers are only known after a Refresh, so their settings aren't filtered
    settings = {tool: s.model_dump() for tool, s in request.settings.items()} if request.settings is not None else current
    await actor.set_mcp_admin(name, request.enabled, settings, current_user.id)
    return room_mcp_view(actor)


@router.post("/{room_id}/mcp/admin/{name}/refresh")
async def refresh_admin(room_id: str, name: str, current_user: User = Depends(require_owner),
                        actor: RoomActor = Depends(get_room_actor_dep)) -> dict[str, Any]:
    spec = _admin_spec(name)
    mcp_catalog.ADMIN_TOOLS[name] = [ToolInfo.from_dict(t) for t in await _tools(spec, room_server=False)]
    return room_mcp_view(actor)
