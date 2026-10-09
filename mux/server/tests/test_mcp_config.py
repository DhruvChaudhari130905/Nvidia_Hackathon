"""mcp.json loading, tool names, room-server URL checks and token encryption."""

import json

import pytest
from cryptography.fernet import Fernet

from mux.config import settings
from mux.mcp.config import ServerSpec, load_admin_servers, parse_servers
from mux.mcp.names import tool_alias, valid_server_name
from mux.mcp.secrets import SecretsUnavailable, decrypt_headers, encrypt_headers
from mux.mcp.urls import UrlNotAllowed, check_url


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


@pytest.mark.parametrize("url", [
    "http://93.184.216.34/mcp",          # not https
    "https://127.0.0.1/mcp",             # loopback
    "https://10.0.0.5/mcp",              # private
    "https://192.168.1.2/mcp",
    "https://169.254.169.254/latest",    # cloud metadata (link-local)
    "https://[::1]/mcp",
    "https://0.0.0.0/mcp",
    "https:///mcp",                      # no host
    "https://100.100.100.200/mcp",       # carrier-grade NAT (Tailscale and cloud internal ranges)
    "https://198.18.0.1/mcp",            # benchmarking range, not public
])
def test_room_server_urls_refused(url, monkeypatch):
    monkeypatch.setattr(settings, "mcp_allow_private_urls", False)
    with pytest.raises(UrlNotAllowed):
        check_url(url)


def test_public_https_url_allowed_and_dev_override(monkeypatch):
    monkeypatch.setattr(settings, "mcp_allow_private_urls", False)
    check_url("https://93.184.216.34/mcp")
    monkeypatch.setattr(settings, "mcp_allow_private_urls", True)
    check_url("http://localhost:8123/mcp")


def test_headers_round_trip_encrypted(monkeypatch):
    monkeypatch.setattr(settings, "mcp_encryption_key", Fernet.generate_key().decode())
    stored = encrypt_headers({"Authorization": "Bearer secret"})
    assert "secret" not in stored["Authorization"]
    assert decrypt_headers(stored) == {"Authorization": "Bearer secret"}


def test_headers_need_a_key(monkeypatch):
    monkeypatch.setattr(settings, "mcp_encryption_key", "")
    assert encrypt_headers({}) == {} and decrypt_headers({}) == {}
    with pytest.raises(SecretsUnavailable):
        encrypt_headers({"Authorization": "x"})
    monkeypatch.setattr(settings, "mcp_encryption_key", "not-a-fernet-key")
    with pytest.raises(SecretsUnavailable):
        encrypt_headers({"Authorization": "x"})


def test_headers_from_another_key_cannot_be_read(monkeypatch):
    monkeypatch.setattr(settings, "mcp_encryption_key", Fernet.generate_key().decode())
    stored = encrypt_headers({"Authorization": "x"})
    monkeypatch.setattr(settings, "mcp_encryption_key", Fernet.generate_key().decode())
    with pytest.raises(SecretsUnavailable):
        decrypt_headers(stored)


@pytest.mark.parametrize("headers", [
    {"Authorization": "Bearer x\n"},
    {"Authorization": "Bearer\x00x"},
    {"Bad Name": "x"},
    {"Authorization": " leading-space"},
])
def test_unsafe_headers_are_refused_in_mcp_json(headers):
    assert parse_servers({"mcpServers": {"docs": {"url": "https://example.com/mcp", "headers": headers}}}) == {}


def test_header_problem():
    from mux.mcp.names import header_problem
    assert header_problem("Authorization", "Bearer abc.def-123") is None
    assert header_problem("X-Api-Key", "") is None
    assert header_problem("Authorization", "Bearer x\r\n") and header_problem("Bad Name", "x")
