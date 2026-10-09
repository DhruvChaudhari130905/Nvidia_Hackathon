"""McpToolset: MCP tools next to the coder's built-in tools for one task."""

from typing import Any

import anyio
import pytest
from mcp.server.mcpserver import MCPServer

import mux.mcp.client as mcp_client
from mux.config import settings
from mux.mcp.config import ServerSpec
from mux.mcp.toolset import ALLOW, DENY, EnabledServer, McpToolset


def make_server() -> MCPServer:
    server = MCPServer("docs")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @server.tool()
    def boom() -> str:
        """Always fails."""
        raise ValueError("boom")

    @server.tool()
    async def slow() -> str:
        """Takes too long."""
        await anyio.sleep(5)
        return "late"

    return server


class FakeInner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def schemas(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": "read_file", "description": "Read", "parameters": {}}}]

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        return {"ok": True, "path": arguments.get("path")}


@pytest.fixture
def servers(monkeypatch):
    available = {"docs": make_server()}

    def connect(spec: ServerSpec):
        if spec.name not in available:
            raise ConnectionError(f"{spec.name} refused the connection")
        return mcp_client.open_client(spec, target=available[spec.name])

    monkeypatch.setattr(mcp_client, "default_connect", connect)
    return available


def docs(settings: dict | None = None, **kw) -> EnabledServer:
    return EnabledServer(ServerSpec("docs", url="https://93.184.216.34/mcp"), settings or {}, **kw)


def names(toolset: McpToolset) -> set[str]:
    return {s["function"]["name"] for s in toolset.schemas()}


def answering(reply: str, questions: list[str]):
    async def ask(question: str) -> str:
        questions.append(question)
        return reply
    return ask


async def test_offers_and_routes_mcp_tools(servers):
    inner = FakeInner()
    async with McpToolset(inner, [docs()]) as toolset:
        assert names(toolset) == {"read_file", "docs__add", "docs__boom", "docs__slow"}
        add = next(s for s in toolset.schemas() if s["function"]["name"] == "docs__add")
        assert add["function"]["description"].startswith("[MCP: docs] Add two numbers.")
        assert set(add["function"]["parameters"]["properties"]) == {"a", "b"}
        result = await toolset.execute("docs__add", {"a": 1, "b": 2})
        assert result["ok"] and "3" in result["content"]
        assert await toolset.execute("read_file", {"path": "a.py"}) == {"ok": True, "path": "a.py"}
        failed = await toolset.execute("docs__boom", {})
        assert failed["ok"] is False and "boom" in failed["error"]
    assert inner.calls == [("read_file", {"path": "a.py"})]


async def test_disabled_tools_are_not_offered(servers):
    async with McpToolset(FakeInner(), [docs({"boom": {"enabled": False}})]) as toolset:
        assert "docs__boom" not in names(toolset) and "docs__add" in names(toolset)


async def test_ask_tools_wait_for_the_room(servers):
    questions: list[str] = []
    async with McpToolset(FakeInner(), [docs({"add": {"mode": "ask"}})], ask=answering(ALLOW, questions)) as toolset:
        assert (await toolset.execute("docs__add", {"a": 2, "b": 2}))["ok"]
        assert (await toolset.execute("docs__boom", {}))["ok"] is False  # auto: no question
    assert len(questions) == 1 and "docs__add" in questions[0] and '"a": 2' in questions[0]

    async with McpToolset(FakeInner(), [docs({"add": {"mode": "ask"}})], ask=answering(DENY, questions)) as toolset:
        denied = await toolset.execute("docs__add", {"a": 2, "b": 2})
    assert denied == {"ok": False, "error": "The room denied this tool call"}


async def test_ask_without_a_room_is_denied(servers):
    async with McpToolset(FakeInner(), [docs({"add": {"mode": "ask"}})]) as toolset:
        assert (await toolset.execute("docs__add", {"a": 1, "b": 1}))["ok"] is False


async def test_calls_time_out(servers):
    async with McpToolset(FakeInner(), [docs()], call_timeout=0.2) as toolset:
        result = await toolset.execute("docs__slow", {})
    assert result["ok"] is False and "timed out" in result["error"]


async def test_unavailable_servers_are_skipped_and_reported(servers):
    reported: list[tuple[str, str]] = []

    async def on_unavailable(name: str, reason: str) -> None:
        reported.append((name, reason))

    down = EnabledServer(ServerSpec("down", url="https://93.184.216.34/mcp"), {})
    async with McpToolset(FakeInner(), [down, docs()], on_unavailable=on_unavailable) as toolset:
        assert "docs__add" in names(toolset) and not any(n.startswith("down__") for n in names(toolset))
    assert reported == [("down", "down refused the connection")]


async def test_room_server_urls_are_checked_again_when_connecting(servers, monkeypatch):
    monkeypatch.setattr(settings, "mcp_allow_private_urls", False)
    reported: list[str] = []

    async def on_unavailable(name: str, reason: str) -> None:
        reported.append(reason)

    private = EnabledServer(ServerSpec("docs", url="https://10.0.0.5/mcp"), {}, room_server=True)
    async with McpToolset(FakeInner(), [private], on_unavailable=on_unavailable) as toolset:
        assert names(toolset) == {"read_file"}
    assert reported and "Private" in reported[0]


async def test_cancelling_while_connecting_closes_servers_already_connected(servers, monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager

    opened: list[str] = []
    closed: list[str] = []
    real = mcp_client.default_connect

    @asynccontextmanager
    async def tracked(spec: ServerSpec):
        if spec.name == "hang":
            await asyncio.sleep(100)
        async with real(spec) as client:
            opened.append(spec.name)
            try:
                yield client
            finally:
                closed.append(spec.name)

    monkeypatch.setattr(mcp_client, "default_connect", tracked)
    hang = EnabledServer(ServerSpec("hang", url="https://93.184.216.34/mcp"), {})

    async def enter() -> None:
        async with McpToolset(FakeInner(), [docs(), hang]):
            pass

    task = asyncio.create_task(enter())
    for _ in range(200):
        if opened:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert opened == ["docs"] and closed == ["docs"]


async def test_room_server_connection_errors_are_generic(servers):
    reported: list[str] = []

    async def on_unavailable(name: str, reason: str) -> None:
        reported.append(reason)

    down = EnabledServer(ServerSpec("down", url="https://93.184.216.34/mcp"), {}, room_server=True)
    async with McpToolset(FakeInner(), [down], on_unavailable=on_unavailable):
        pass
    assert reported == ["could not reach the server"]
