"""MCP tools next to the coder's built-in tools, for one coder task.

Each enabled server gets its own connection task: it connects, lists the tools, holds the connection until
the task ends, then closes it. The SDK's connections must be opened and closed in one task, and a transport
failure cancels that task; keeping it apart from the coder's task means a server that hangs, crashes or
restarts only fails its own calls. Servers connect in parallel within CONNECT_TIMEOUT. Tools are offered as
<server>__<tool>; tools set to "ask" wait for the room first.
"""

from __future__ import annotations

import asyncio
import json
import logging
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


CLOSE_TIMEOUT = 5.0


@dataclass(eq=False)
class _Connection:
    server: EnabledServer
    ready: asyncio.Future[tuple[Client, list[ToolInfo]]]
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    task: Optional[asyncio.Task[None]] = None
    lost: Optional[str] = None  # why the connection dropped after it was up

    def describe(self, error: BaseException) -> str:
        spec = self.server.spec
        secrets = [*spec.headers.values(), *spec.env.values()]
        return describe_error(error, secrets=secrets, room_server=self.server.room_server)


@dataclass(frozen=True)
class _Route:
    connection: _Connection
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
        self._connections: list[_Connection] = []

    async def __aenter__(self) -> "McpToolset":
        loop = asyncio.get_running_loop()
        try:
            self._connections = [_Connection(server, loop.create_future()) for server in self.servers]
            for connection in self._connections:
                connection.task = asyncio.create_task(self._hold(connection))
            if self._connections:
                await asyncio.wait([c.ready for c in self._connections], timeout=mcp_client.CONNECT_TIMEOUT)
            taken = {s["function"]["name"] for s in self.inner.schemas()}
            for connection in self._connections:
                name = connection.server.spec.name
                if not connection.ready.done():
                    connection.ready.cancel()
                    reason = connection.describe(TimeoutError())
                elif (error := connection.ready.exception()) is not None:
                    reason = connection.describe(error)
                else:
                    client, tools = connection.ready.result()
                    for tool in tools:
                        setting = tool_setting(connection.server.settings, tool.name)
                        if setting.enabled:
                            alias = tool_alias(name, tool.name, taken)
                            self._routes[alias] = _Route(connection, client, name, tool, setting.mode)
                    continue
                connection.stop.set()
                logger.warning(f"MCP server {name} unavailable: {reason}")
                if self._on_unavailable is not None:
                    await self._on_unavailable(name, reason)
        except BaseException:
            await self._close()  # cancelled while connecting (the room stopped): close what did connect
            raise
        return self

    async def _hold(self, connection: _Connection) -> None:
        """Connect, hand the client over, keep it open until the task ends, close it. Never raises."""
        spec = connection.server.spec
        try:
            if connection.server.room_server and spec.url:
                await check_url_async(spec.url)
            async with mcp_client.default_connect(spec) as client:
                tools = await list_tools(client)
                if not connection.ready.done():
                    connection.ready.set_result((client, tools))
                await connection.stop.wait()
        except BaseException as e:  # including the cancellation a transport failure sends this task
            if not connection.ready.done():
                connection.ready.set_exception(e if isinstance(e, Exception) else ConnectionError("connection closed"))
            elif not connection.stop.is_set():
                connection.lost = connection.describe(e)
                logger.warning(f"MCP server {spec.name} disconnected: {connection.lost}")

    async def _close(self) -> None:
        tasks = [c.task for c in self._connections if c.task is not None]
        for connection in self._connections:
            connection.stop.set()
        if not tasks:
            return
        _, pending = await asyncio.wait(tasks, timeout=CLOSE_TIMEOUT)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending, timeout=CLOSE_TIMEOUT)

    async def __aexit__(self, *exc: Any) -> None:
        await self._close()

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
        connection = route.connection
        if connection.lost is not None:
            return {"ok": False, "error": f"MCP server {route.server} disconnected: {connection.lost}"}
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
            await asyncio.sleep(0)  # let the connection task record why it dropped
            reason = connection.lost or connection.describe(e)
            return {"ok": False, "error": reason}
        return result_payload(result)
