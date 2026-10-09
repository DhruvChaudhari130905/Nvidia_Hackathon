"""MCP tools next to the coder's built-in tools, for one coder task.

Connects to each enabled server when the task starts (in turn: the SDK's connections must be opened and
closed in this same task), offers their enabled tools as <server>__<tool>, routes calls to the right
session, asks the room first for tools set to "ask", and closes every connection when the task ends.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Optional, Protocol

from mcp import Client

import mux.mcp.client as mcp_client
from mux.mcp.client import CALL_TIMEOUT, ToolInfo, describe_error, list_tools, result_payload
from mux.mcp.config import ServerSpec
from mux.mcp.names import tool_alias
from mux.mcp.urls import check_url_async

logger = logging.getLogger(__name__)

ALLOW = "Allow"
DENY = "Deny"
Mode = Literal["auto", "ask"]


@dataclass(frozen=True)
class ToolSetting:
    enabled: bool = True
    mode: Mode = "auto"


def tool_setting(settings: dict[str, dict[str, Any]], tool: str) -> ToolSetting:
    raw = settings.get(tool) or {}
    return ToolSetting(enabled=bool(raw.get("enabled", True)), mode="ask" if raw.get("mode") == "ask" else "auto")


@dataclass(frozen=True)
class EnabledServer:
    spec: ServerSpec
    settings: dict[str, dict[str, Any]] = field(default_factory=dict)
    room_server: bool = False  # added by the room's owner: its URL is checked again before connecting


class _Executor(Protocol):
    def schemas(self) -> list[dict[str, Any]]: ...
    async def execute(self, name: str, arguments: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class _Route:
    client: Client
    server: str
    tool: ToolInfo
    mode: Mode


class McpToolset:
    def __init__(
        self,
        inner: _Executor,
        servers: list[EnabledServer],
        *,
        ask: Optional[Callable[[str], Awaitable[str]]] = None,
        on_unavailable: Optional[Callable[[str, str], Awaitable[None]]] = None,
        call_timeout: float = CALL_TIMEOUT,
    ) -> None:
        self.inner = inner
        self.servers = servers
        self._ask = ask
        self._on_unavailable = on_unavailable
        self.call_timeout = call_timeout
        self._routes: dict[str, _Route] = {}
        self._stack = AsyncExitStack()

    async def __aenter__(self) -> "McpToolset":
        await self._stack.__aenter__()
        taken = {s["function"]["name"] for s in self.inner.schemas()}
        for server in self.servers:
            try:
                tools, client = await self._connect(server)
            except Exception as e:
                reason = describe_error(e)
                logger.warning(f"MCP server {server.spec.name} unavailable: {reason}")
                if self._on_unavailable is not None:
                    await self._on_unavailable(server.spec.name, reason)
                continue
            for tool in tools:
                setting = tool_setting(server.settings, tool.name)
                if setting.enabled:
                    alias = tool_alias(server.spec.name, tool.name, taken)
                    self._routes[alias] = _Route(client, server.spec.name, tool, setting.mode)
        return self

    async def _connect(self, server: EnabledServer) -> tuple[list[ToolInfo], Client]:
        if server.room_server and server.spec.url:
            await check_url_async(server.spec.url)
        async with asyncio.timeout(mcp_client.CONNECT_TIMEOUT):
            client = await self._stack.enter_async_context(mcp_client.default_connect(server.spec))
            return await list_tools(client), client

    async def __aexit__(self, *exc: Any) -> None:
        await self._stack.__aexit__(*exc)

    def schemas(self) -> list[dict[str, Any]]:
        extra = [{
            "type": "function",
            "function": {
                "name": alias,
                "description": f"[MCP: {route.server}] {route.tool.description}".strip()[:1024],
                "parameters": route.tool.input_schema or {"type": "object", "properties": {}},
            },
        } for alias, route in self._routes.items()]
        return self.inner.schemas() + extra

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        route = self._routes.get(name)
        if route is None:
            return await self.inner.execute(name, arguments)
        if route.mode == "ask":
            shown = json.dumps(arguments)[:500]
            question = f"The coder wants to use {name} (MCP server {route.server}) with {shown}. Allow it?"
            if self._ask is None or await self._ask(question) != ALLOW:
                return {"ok": False, "error": "The room denied this tool call"}
        try:
            async with asyncio.timeout(self.call_timeout):
                result = await route.client.call_tool(route.tool.name, arguments)
        except TimeoutError:
            return {"ok": False, "error": f"{name} timed out after {self.call_timeout:g}s"}
        except Exception as e:
            return {"ok": False, "error": describe_error(e)}
        return result_payload(result)
