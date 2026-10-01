"""Tavily client with a per-room query cache."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from tavily import AsyncTavilyClient

from mux.config import settings

@dataclass
class Source:
    title: str
    url: str
    snippet: str

@dataclass
class SearchResult:
    query: str
    answer: str #Tavily's short answer, "" when it gives none
    sources: list[Source] = field(default_factory=list)

class WebSearch(Protocol):
    async def search(self, query: str) -> SearchResult: ...

class TavilySearch:
    """One instance per room, so the cache is per room. Share one AsyncTavilyClient across rooms."""
    def __init__(self, client: Any| None = None, *, max_results: int = 3, snippet_chars: int= 300) ->None:
        self._client = client or AsyncTavilyClient(api_key=settings.tavily_api_key)
        self._max_results = max_results
        self._snippet_chars = snippet_chars
        self._cache: dict[str, SearchResult] = {}

    async def search(self, query: str) -> SearchResult:
        key = " ".join(query.lower().split())
        if key in self._cache:
            return self._cache[key]
        raw = await self._client.search(
            query, search_depth="basic", max_results=self._max_results, include_answer = True,
        )
        result = SearchResult(
            query = query,
            answer = raw.get("answer") or "",
            sources = [
                Source(r.get("title", ""), r["url"], _shorten(r.get("content", ""), self._snippet_chars))
                for r in raw.get("results", [])
                if r.get("url")
            ],
        )
        self._cache[key] = result
        return result
    
def _shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"