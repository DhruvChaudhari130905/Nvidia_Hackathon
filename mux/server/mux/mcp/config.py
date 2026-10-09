"""Server-wide MCP servers from mcp.json (the format Claude Desktop uses), set up by whoever runs MUX."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Literal, Optional

from mux.config import settings
from mux.mcp.names import valid_server_name

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServerSpec:
    """One MCP server: a command to run (stdio) or a URL (streamable HTTP)."""
    name: str
    url: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    command: Optional[str] = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)

    @property
    def kind(self) -> Literal["stdio", "http"]:
        return "stdio" if self.command else "http"


def _str_map(value: Any) -> Optional[dict[str, str]]:
    if value is None:
        return {}
    if isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        return dict(value)
    return None


def _parse(name: Any, entry: Any) -> tuple[Optional[ServerSpec], str]:
    """(spec, "") or (None, why it was skipped)."""
    if not isinstance(name, str) or not valid_server_name(name):
        return None, "names use a-z, 0-9, _ and - (at most 32 characters)"
    if not isinstance(entry, dict):
        return None, "must be an object"
    command, url = entry.get("command"), entry.get("url")
    if (command is None) == (url is None):
        return None, 'needs either "command" or "url"'
    if command is not None:
        args = entry.get("args", [])
        env = _str_map(entry.get("env"))
        if not isinstance(command, str) or not command:
            return None, '"command" must be a string'
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            return None, '"args" must be a list of strings'
        if env is None:
            return None, '"env" must map strings to strings'
        return ServerSpec(name, command=command, args=tuple(args), env=env), ""
    headers = _str_map(entry.get("headers"))
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None, '"url" must start with http:// or https://'
    if headers is None:
        return None, '"headers" must map strings to strings'
    return ServerSpec(name, url=url, headers=headers), ""


def parse_servers(data: Any) -> dict[str, ServerSpec]:
    entries = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(entries, dict):
        logger.error('mcp.json: expected {"mcpServers": {...}}; no server-wide MCP servers')
        return {}
    servers: dict[str, ServerSpec] = {}
    for name, entry in entries.items():
        spec, problem = _parse(name, entry)
        if spec is None:
            logger.error(f"mcp.json: skipping {name!r}: {problem}")
            continue
        servers[spec.name] = spec
    return servers


def load_admin_servers(path: Path) -> dict[str, ServerSpec]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.error(f"{path}: unreadable, no server-wide MCP servers: {e}")
        return {}
    return parse_servers(data)


@cache
def admin_servers() -> dict[str, ServerSpec]:
    """The server-wide servers, read once (restart the server after editing mcp.json)."""
    return load_admin_servers(Path(settings.mcp_config_path))
