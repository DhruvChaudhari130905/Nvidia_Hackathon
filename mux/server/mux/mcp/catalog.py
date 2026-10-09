"""A room's MCP servers: what the coder connects to, and what the room's Tools panel shows."""

from __future__ import annotations

import logging
from typing import Any

import mux.mcp.config as mcp_config
from mux.mcp.client import ToolInfo
from mux.mcp.config import ServerSpec
from mux.secrets import SecretsUnavailable, decrypt_values
from mux.mcp.toolset import EnabledServer
from mux.mcp.views import server_view
from mux.rooms.actor import RoomActor

logger = logging.getLogger(__name__)

# Server-wide servers' tool lists, loaded by an owner's Refresh (shared by every room; lost on restart)
ADMIN_TOOLS: dict[str, list[ToolInfo]] = {}


def enabled_servers(actor: RoomActor) -> list[EnabledServer]:
    """The servers the coder connects to in this room: switched-on mcp.json servers, then the room's own."""
    admin = mcp_config.admin_servers()
    servers = [EnabledServer(admin[name], cfg.get("settings") or {})
               for name, cfg in sorted(actor.mcp_admin.items()) if cfg.get("enabled") and name in admin]
    for name, server in sorted(actor.mcp_servers.items()):
        try:
            headers = decrypt_values(server.get("headers") or {})
        except SecretsUnavailable as e:
            logger.warning(f"Room {actor.room_id}: skipping MCP server {name}: {e}")
            continue
        servers.append(EnabledServer(ServerSpec(name, url=server["url"], headers=headers),
                                     server.get("settings") or {}, room_server=True))
    return servers


def room_mcp_view(actor: RoomActor) -> dict[str, Any]:
    admin = []
    for name, spec in sorted(mcp_config.admin_servers().items()):
        cfg = actor.mcp_admin.get(name) or {}
        admin.append({
            "name": name, "kind": spec.kind, "enabled": bool(cfg.get("enabled")), "settings": cfg.get("settings") or {},
            "tools": [t.to_dict() for t in ADMIN_TOOLS.get(name, [])], "tools_loaded": name in ADMIN_TOOLS,
        })
    return {"admin": admin, "servers": [server_view(n, s) for n, s in sorted(actor.mcp_servers.items())]}
