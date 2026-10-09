"""mcp.json loading and tool names."""

import json

from mux.mcp.config import ServerSpec, load_admin_servers, parse_servers
from mux.mcp.names import tool_alias, valid_server_name


def test_parses_stdio_and_http_servers():
    servers = parse_servers({"mcpServers": {
        "github": {"command": "npx", "args": ["-y", "server-github"], "env": {"TOKEN": "t"}},
        "docs": {"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer x"}},
    }})
    assert servers["github"] == ServerSpec("github", command="npx", args=("-y", "server-github"), env={"TOKEN": "t"})
    assert servers["github"].kind == "stdio"
    assert servers["docs"].kind == "http" and servers["docs"].headers == {"Authorization": "Bearer x"}


def test_invalid_entries_are_skipped():
    servers = parse_servers({"mcpServers": {
        "Bad Name": {"command": "x"},
        "neither": {},
        "both": {"command": "x", "url": "https://a"},
        "badurl": {"url": "ftp://a"},
        "badargs": {"command": "x", "args": "not-a-list"},
        "badenv": {"command": "x", "env": {"A": 1}},
        "ok": {"command": "x"},
    }})
    assert list(servers) == ["ok"]


def test_missing_or_broken_file_means_no_servers(tmp_path):
    assert load_admin_servers(tmp_path / "missing.json") == {}
    broken = tmp_path / "mcp.json"
    broken.write_text("{not json")
    assert load_admin_servers(broken) == {}
    broken.write_text(json.dumps({"servers": {}}))
    assert load_admin_servers(broken) == {}


def test_server_names():
    assert valid_server_name("github") and valid_server_name("my_docs-2")
    assert not valid_server_name("GitHub") and not valid_server_name("") and not valid_server_name("a" * 33)


def test_tool_alias_is_safe_short_and_unique():
    taken: set[str] = set()
    assert tool_alias("docs", "search.pages", taken) == "docs__search_pages"
    assert tool_alias("docs", "search pages", taken) == "docs__search_pages_2"
    long = tool_alias("docs", "x" * 100, taken)
    assert len(long) == 64 and long.startswith("docs__")
    assert len(taken) == 3
