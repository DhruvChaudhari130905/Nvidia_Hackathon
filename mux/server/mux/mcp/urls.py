"""Which URLs a room owner may point MUX at: public https only, so a room can't reach the server's network."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from mux.config import settings


class UrlNotAllowed(ValueError):
    pass


def check_url(url: str) -> None:
    """Raise UrlNotAllowed unless `url` is https and its host resolves only to public addresses.

    MCP_ALLOW_PRIVATE_URLS=true (local development) allows http and private addresses.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme not in ("http", "https") or not host:
        raise UrlNotAllowed("Use an https:// URL")
    if settings.mcp_allow_private_urls:
        return
    if parsed.scheme != "https":
        raise UrlNotAllowed("Use an https:// URL")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as e:
        raise UrlNotAllowed(f"Can't find {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # is_global also rules out shared ranges that aren't "private", like 100.64.0.0/10 (Tailscale)
        if (not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified
                or ip.is_reserved or ip.is_multicast):
            raise UrlNotAllowed("Private and local network addresses aren't allowed")


async def check_url_async(url: str) -> None:
    """check_url without blocking the event loop on DNS."""
    await asyncio.to_thread(check_url, url)
