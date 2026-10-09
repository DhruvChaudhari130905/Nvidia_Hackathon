"""Connecting to one MCP server with the SDK, listing its tools, and turning results into tool output.

The only module that knows the SDK. Everything else goes through `default_connect` (read at call time,
so tests can swap in an in-process server).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CallToolResult

from mux.mcp.config import ServerSpec

CONNECT_TIMEOUT = 10.0
CALL_TIMEOUT = 60.0
MAX_RESULT_CHARS = 20_000


@dataclass(frozen=True)
class ToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolInfo":
        return cls(str(data["name"]), str(data.get("description") or ""), dict(data.get("input_schema") or {}))


Connect = Callable[[ServerSpec], AbstractAsyncContextManager[Client]]


@asynccontextmanager
async def open_client(spec: ServerSpec, target: Any = None) -> AsyncIterator[Client]:
    """A connected client for `spec`. `target` replaces the transport (tests pass an in-process MCPServer)."""
    async with AsyncExitStack() as stack:
        if target is None:
            if spec.command:
                target = StdioServerParameters(command=spec.command, args=list(spec.args), env=spec.env or None)
            else:
                if not spec.url:
                    raise ValueError(f"MCP server {spec.name} has neither a command nor a URL")
                http = await stack.enter_async_context(httpx2.AsyncClient(headers=spec.headers, timeout=CALL_TIMEOUT))
                target = streamable_http_client(spec.url, http_client=http)
        yield await stack.enter_async_context(Client(target, read_timeout_seconds=CALL_TIMEOUT))


default_connect: Connect = open_client


async def list_tools(client: Client) -> list[ToolInfo]:
    tools: list[ToolInfo] = []
    cursor: str | None = None
    while True:
        page = await client.list_tools(cursor=cursor)
        tools += [ToolInfo(t.name, t.description or "", dict(t.input_schema)) for t in page.tools]
        cursor = page.next_cursor
        if not cursor:
            return tools


async def fetch_tools(spec: ServerSpec) -> list[ToolInfo]:
    """Connect, list the tools, disconnect. Raises on failure (TimeoutError after CONNECT_TIMEOUT)."""
    async with asyncio.timeout(CONNECT_TIMEOUT):
        async with default_connect(spec) as client:
            return await list_tools(client)


def result_payload(result: CallToolResult) -> dict[str, Any]:
    """A tool result as the coder sees it: {"ok", "content"} or {"ok": False, "error"}."""
    parts = [block.text if isinstance(getattr(block, "text", None), str) else f"[{block.type} content omitted]"
             for block in result.content]
    if not parts and result.structured_content is not None:
        parts.append(json.dumps(result.structured_content))
    text = "\n".join(parts)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + f"\n[cut: {len(text) - MAX_RESULT_CHARS} more characters]"
    if result.is_error:
        return {"ok": False, "error": text or "the tool reported an error"}
    return {"ok": True, "content": text or "(no output)"}


def describe_error(error: BaseException) -> str:
    """A short reason for a failed connect or call (anyio wraps errors in exception groups)."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    if isinstance(error, TimeoutError):
        return "timed out"
    return str(error) or type(error).__name__
