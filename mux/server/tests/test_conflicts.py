
"""Tests for conflict research and vote tallies."""

import asyncio

from mux.agents.coordinator.conflicts import Vote, research_conflict, tally, vote_weight
from mux.agents.coordinator.schema import OpenConflict
from mux.agents.llm import ModelRole
from mux.integrations.tavily import SearchResult, Source, TavilySearch
from mux.replay.fake_llm import FakeLLM

A = Source("Auth guide", "https://a.dev", "Login reduces spam RSVPs.")
B = Source("Privacy post", "https://b.dev", "Anonymous forms get more replies.")
CONFLICT = OpenConflict(
    with_message_ids=["m1"], summary="Google login vs anonymous RSVPs",
    options=["Google login", "Anonymous"], research_queries=["rsvp login spam", "anonymous form response rate"],
)


class FakeSearch:
    def __init__(self, results: dict[str, SearchResult | Exception]) -> None:
        self.results = results
        self.queries: list[str] = []

    async def search(self, query: str) -> SearchResult:
        self.queries.append(query)
        r = self.results[query]
        if isinstance(r, Exception):
            raise r
        return r


def research(search, *script, conflict=CONFLICT):
    llm = FakeLLM(list(script))
    return asyncio.run(research_conflict(llm, search, conflict)), llm


SEARCH = FakeSearch({
    "rsvp login spam": SearchResult("rsvp login spam", "Login cuts spam.", [A, B]),
    "anonymous form response rate": SearchResult("anonymous form response rate", "", [B]),
})
GOOD = '{"summary": "Login cuts spam [1]; anonymous gets more replies [2].", "citations": [{"title": "Auth guide", "url": "https://a.dev"}]}'


def test_research_runs_queries_and_numbers_unique_sources():
    r, llm = research(SEARCH, GOOD)
    assert r.evidence is not None and r.evidence.citations[0].url == "https://a.dev"
    assert r.queries == ["rsvp login spam", "anonymous form response rate"] and not r.fallback
    user = llm.calls[0].messages[1]["content"]
    assert "[1] Auth guide (https://a.dev)" in user and "[2] Privacy post (https://b.dev)" in user
    assert "[3]" not in user  # https://b.dev came back twice but is listed once
    assert llm.calls[0].role is ModelRole.SUPER


def test_research_rejects_made_up_urls():
    made_up = GOOD.replace("https://a.dev", "https://fake.dev")
    r, llm = research(SEARCH, made_up, GOOD)
    assert r.evidence is not None and r.evidence.citations[0].url == "https://a.dev"
    assert "https://fake.dev" in llm.calls[1].messages[-1]["content"]


def test_research_falls_back_to_tavily_answer():
    r, _ = research(SEARCH, "nope", "nope")
    assert r.fallback and r.evidence is not None
    assert r.evidence.summary == "Login cuts spam."
    assert [c.url for c in r.evidence.citations] == ["https://a.dev", "https://b.dev"]


def test_research_skips_failed_query_and_handles_no_sources():
    failing = FakeSearch({"rsvp login spam": TimeoutError("down"), "anonymous form response rate": SearchResult("q", "", [])})
    r, llm = research(failing)
    assert r.evidence is None and llm.calls == []


def test_research_uses_summary_when_no_queries():
    search = FakeSearch({CONFLICT.summary: SearchResult(CONFLICT.summary, "", [A])})
    r, _ = research(search, GOOD, conflict=CONFLICT.model_copy(update={"research_queries": []}))
    assert search.queries == [CONFLICT.summary] and r.evidence is not None


class FakeTavilyClient:
    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query, **kwargs):
        self.calls += 1
        return {"answer": "yes", "results": [{"title": "T", "url": "https://t.dev", "content": "word " * 200}, {"title": "no url"}]}


def test_tavily_search_caches_and_shortens():
    client = FakeTavilyClient()
    s = TavilySearch(client, snippet_chars=50)
    first = asyncio.run(s.search("RSVP  Login"))
    second = asyncio.run(s.search("rsvp login"))
    assert client.calls == 1 and first is second
    assert first.answer == "yes" and len(first.sources) == 1
    assert len(first.sources[0].snippet) <= 50 and first.sources[0].snippet.endswith("…")


# votes

OPTIONS = ["Google login", "Anonymous"]


def test_weight_doubles_for_domain_role():
    assert vote_weight("pm", "scope") == 2 and vote_weight("eng", "scope") == 1 and vote_weight(None, "ui") == 1


def test_domain_role_outweighs_one_other_voter():
    t = tally(OPTIONS, [Vote("u1", "Google login", "pm"), Vote("u2", "Anonymous", "eng")], "scope", owner_id="u9")
    assert t.winner == "Google login" and t.totals == {"Google login": 2, "Anonymous": 1} and t.decided_by == "votes"


def test_tie_goes_to_owner():
    t = tally(OPTIONS, [Vote("owner", "Anonymous", "eng"), Vote("u2", "Google login", "design")], "scope", owner_id="owner")
    assert t.winner == "Anonymous" and t.decided_by == "owner"


def test_tie_without_owner_goes_to_domain_voter():
    votes = [Vote("u1", "Google login", "pm"), Vote("u2", "Anonymous", "eng"), Vote("u3", "Anonymous", "design")]
    t = tally(OPTIONS, votes, "scope", owner_id="owner")
    assert t.winner == "Google login" and t.decided_by == "domain"


def test_unbreakable_tie_and_no_votes():
    t = tally(OPTIONS, [Vote("u1", "Google login", "eng"), Vote("u2", "Anonymous", "eng")], "scope", owner_id="owner")
    assert t.winner is None and t.decided_by == "tie"
    assert tally(OPTIONS, [], "scope", owner_id="owner").winner is None


def test_later_vote_replaces_earlier_and_unknown_option_ignored():
    votes = [Vote("u1", "Google login", None), Vote("u1", "Anonymous", None), Vote("u2", "Pizza", None)]
    t = tally(OPTIONS, votes, "ui", owner_id="owner")
    assert t.totals == {"Google login": 0, "Anonymous": 1} and t.winner == "Anonymous"
