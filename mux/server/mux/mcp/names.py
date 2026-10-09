"""Server names, and the names MCP tools get when offered to the model."""

from __future__ import annotations

import re

_SERVER_NAME = re.compile(r"^[a-z0-9_-]{1,32}$")
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")
# RFC 9110 field names; values are visible ASCII with inner spaces. Anything else makes the HTTP library
# fail with the value in its error message, which would put a token in logs and the room feed.
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,100}$")
_HEADER_VALUE = re.compile(r"^(?:[\x21-\x7e](?:[\x20-\x7e]{0,4094}[\x21-\x7e])?)?$")
MAX_TOOL_NAME = 64


def valid_server_name(name: str) -> bool:
    return bool(_SERVER_NAME.fullmatch(name))


def header_problem(name: str, value: str) -> str | None:
    """Why this header can't be sent, or None."""
    if not _HEADER_NAME.fullmatch(name):
        return f"header name {name!r} isn't valid"
    if not _HEADER_VALUE.fullmatch(value):
        return f"the value of {name} has spaces at the ends or characters that aren't allowed"
    return None


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
