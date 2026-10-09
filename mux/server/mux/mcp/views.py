"""What browsers may see of a room's MCP server: header names, never their values."""

from __future__ import annotations

from typing import Any


def server_view(name: str, server: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "url": server["url"],
        "header_names": sorted(server.get("headers") or {}),
        "tools": server.get("tools") or [],
        "settings": server.get("settings") or {},
    }
