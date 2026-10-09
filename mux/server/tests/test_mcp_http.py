"""McpToolset against a real streamable-HTTP server: a failing server fails the call, never the coder's task."""

import asyncio
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import mux.mcp.client as mcp_client
from mux.config import settings
from mux.mcp.config import ServerSpec
from mux.mcp.toolset import EnabledServer, McpToolset


class Inner:
    def schemas(self) -> list[dict[str, Any]]:
        return []

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        return {"ok": True}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def http_server(monkeypatch):
    monkeypatch.setattr(settings, "mcp_allow_private_urls", True)
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(Path(__file__).parent / "mcp_http_server.py"), str(port)])
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            import time
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}/mcp"
    proc.kill()
    proc.wait()


def server(url: str) -> list[EnabledServer]:
    return [EnabledServer(ServerSpec("s", url=url))]


async def test_a_hung_http_tool_fails_the_call_not_the_task(http_server, monkeypatch):
    # The HTTP read timeout fires in the transport's background task after the call has given up
    monkeypatch.setattr(mcp_client, "HTTP_READ_TIMEOUT", 1.0)
    async with McpToolset(Inner(), server(http_server), call_timeout=0.5) as toolset:
        hung = await toolset.execute("s__slow", {})
        assert hung["ok"] is False and "timed out" in hung["error"]
        await asyncio.sleep(1.5)
        after = await toolset.execute("s__ok", {})
    assert isinstance(after, dict) and "ok" in after


async def test_a_server_crash_mid_call_fails_the_call_not_the_task(http_server):
    async with McpToolset(Inner(), server(http_server)) as toolset:
        crashed = await toolset.execute("s__die", {})
        assert crashed["ok"] is False
        await asyncio.sleep(0.5)
        again = await toolset.execute("s__ok", {})
    assert again["ok"] is False
