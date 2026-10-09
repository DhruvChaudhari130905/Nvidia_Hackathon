"""The MCP SDK wrapper, against an in-process server."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, ImageContent, TextContent

import mux.mcp.client as mcp_client
from mux.mcp.client import MAX_RESULT_CHARS, ToolInfo, describe_error, list_tools, open_client, result_payload
from mux.mcp.config import ServerSpec


def make_server() -> MCPServer:
    server = MCPServer("test")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @server.tool()
    def boom() -> str:
        """Always fails."""
        raise ValueError("boom")

    return server


async def test_lists_tools_with_schemas():
    async with open_client(ServerSpec("docs"), target=make_server()) as client:
        tools = await list_tools(client)
    by_name = {t.name: t for t in tools}
    assert set(by_name) == {"add", "boom"}
    assert by_name["add"].description == "Add two numbers."
    assert set(by_name["add"].input_schema["properties"]) == {"a", "b"}
    assert ToolInfo.from_dict(by_name["add"].to_dict()) == by_name["add"]


async def test_call_results_become_tool_output():
    async with open_client(ServerSpec("docs"), target=make_server()) as client:
        ok = result_payload(await client.call_tool("add", {"a": 1, "b": 2}))
        failed = result_payload(await client.call_tool("boom", {}))
    assert ok["ok"] is True and "3" in ok["content"]
    assert failed["ok"] is False and "boom" in failed["error"]


def test_non_text_and_long_results():
    image = CallToolResult(content=[ImageContent(data="aGk=", mime_type="image/png")])
    assert result_payload(image) == {"ok": True, "content": "[image content omitted]"}
    structured = CallToolResult(content=[], structured_content={"rows": 2})
    assert result_payload(structured) == {"ok": True, "content": '{"rows": 2}'}
    empty = CallToolResult(content=[])
    assert result_payload(empty) == {"ok": True, "content": "(no output)"}
    long = result_payload(CallToolResult(content=[TextContent(text="x" * (MAX_RESULT_CHARS + 5))]))
    assert len(long["content"]) < MAX_RESULT_CHARS + 100 and long["content"].endswith("[cut: 5 more characters]")


def test_describe_error_unwraps_groups():
    assert describe_error(ExceptionGroup("g", [ConnectionError("refused")])) == "refused"
    assert describe_error(TimeoutError()) == "timed out"
    assert describe_error(RuntimeError()) == "RuntimeError"


async def test_fetch_tools_uses_default_connect(monkeypatch):
    monkeypatch.setattr(mcp_client, "default_connect", lambda spec: open_client(spec, target=make_server()))
    assert {t.name for t in await mcp_client.fetch_tools(ServerSpec("docs"))} == {"add", "boom"}


async def test_connect_gives_up_after_the_timeout(monkeypatch):
    @asynccontextmanager
    async def never_ready(spec):
        await asyncio.sleep(10)
        yield None

    monkeypatch.setattr(mcp_client, "CONNECT_TIMEOUT", 0.1)
    monkeypatch.setattr(mcp_client, "default_connect", never_ready)
    with pytest.raises(TimeoutError):
        await mcp_client.fetch_tools(ServerSpec("slow"))


def test_describe_error_hides_header_values():
    secret = "Bearer SEC\nRET"
    error = ValueError(f"Illegal header value {secret.encode()!r} and {secret!r} and {secret}")
    text = describe_error(error, secrets=[secret])
    assert "SEC" not in text and "[hidden]" in text
