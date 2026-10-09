"""Server names, and the names MCP tools get when offered to the model."""

from __future__ import annotations

import re

_SERVER_NAME = re.compile(r"^[a-z0-9_-]{1,32}$")
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")
MAX_TOOL_NAME = 64


def valid_server_name(name: str) -> bool:
    return bool(_SERVER_NAME.match(name))


def tool_alias(server: str, tool: str, taken: set[str]) -> str:
    """`<server>__<tool>`, made safe for function names, at most 64 characters and not already in `taken`."""
    base = _UNSAFE.sub("_", f"{server}__{tool}")[:MAX_TOOL_NAME]
    alias, n = base, 2
    while alias in taken:
        suffix = f"_{n}"
        alias = base[: MAX_TOOL_NAME - len(suffix)] + suffix
        n += 1
    taken.add(alias)
    return alias
