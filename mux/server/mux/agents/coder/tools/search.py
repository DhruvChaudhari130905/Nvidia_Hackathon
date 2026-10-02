"""web_search through the shared Tavily client (per-room cache in mux.integrations.tavily)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mux.integrations.tavily import WebSearch


async def web_search(search: WebSearch | None, query: str) -> dict[str, Any]:
    """Return Tavily's short answer plus 2-3 snippets with URLs."""
    query = query.strip()
    if not query:
        return {"ok": False, "error": "query is required"}
    if search is None:
        return {"ok": False, "error": "web search is not configured"}
    result = await search.search(query)
    return {
        "ok": True,
        "query": result.query,
        "answer": result.answer,
        "results": [asdict(source) for source in result.sources],
    }
