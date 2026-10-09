"""A real streamable-HTTP MCP server for tests/test_mcp_http.py: python mcp_http_server.py <port>."""

import os
import sys

import anyio
import uvicorn
from mcp.server.mcpserver import MCPServer

server = MCPServer("t")


@server.tool()
async def slow() -> str:
    """Never finishes."""
    await anyio.sleep(1000)
    return "late"


@server.tool()
def die() -> str:
    """Crashes the server mid-call."""
    os._exit(1)


@server.tool()
def ok() -> str:
    """Works."""
    return "fine"


if __name__ == "__main__":
    uvicorn.run(server.streamable_http_app(), host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
