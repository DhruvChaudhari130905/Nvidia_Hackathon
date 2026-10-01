"""open_conflict and research_conflict (1 to 3 Tavily queries, cited summary). Vote tally with role weighting, 60 s timeout, owner override."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from mux.agents.coordinator.agent import ask_json
from mux.agents.coordinator.schema import Citation, Domain, DomainRole, OpenConflict, ResearchSummary
from mux.agents.llm import LLM, ModelRole, Usage
from mux.integrations.tavily import Source, WebSearch

MAX_QUERIES = 3
MAX_SOURCES = 6


#the domain role whose cote counts double in each conflict domain
DOMAIN_OWNER: dict[Domain, DomainRole] = {"ui": "design", "architecture": "eng", "scope": "pm"}

RESEARCH_SYSTEM = """You help a team settle a disagreement before they vote. You get the disagreement, the options, and numbered web sources.

Write a neutral summary of at most 4 sentences: what the sources say for and against each option. Cite sources inline as [1], [2]. Do not pick a winner. Use only the sources given.

Answer with JSON only:
{"summary": "...", "citations": [{"title": "...", "url": "..."}]}
List in "citations" only the sources you cited, with their exact url."""

#research
@dataclass
class Research:
    evidence: ResearchSummary | None # none when the web search found nothing
    queries: list[str]
    usage: Usage = field(default_factory = Usage)
    fallback: bool = False #true when the model filed twice and Tavilys own answer was used

async def research_conflict(
        llm: LLM, search: WebSearch, conflict: OpenConflict, *, role: ModelRole = ModelRole.SUPER,) -> Research:
    # a failed query is skipped, so one Tavily error does not block the vote
    queries = conflict.research_queries[:MAX_QUERIES] or [conflict.summary]
    results = await asyncio.gather(*(search.search(q) for q in queries), return_exceptions=True)
    found = [r for r in results if not isinstance(r, BaseException)]
    sources = _unique_sources([s for r in found for s in r.sources])
    if not sources:
        return Research(None, queries)
    
    allowed = {s.url for s in sources}
    result = await ask_json(
        llm, role, _research_messages(conflict, sources), ResearchSummary,
        check = lambda summary: _unknown_urls(summary, allowed), max_tokens = 600,
    )
    if result.value is None:
        answers = " ".join(r.answer for r in found if r.answer) or "See the sources below."
        evidence = ResearchSummary(summary=answers, citations=[Citation(title=s.title, url=s.url) for s in sources[:3]])
        return Research(evidence, queries, result.usage, fallback=True)
    return Research(result.value, queries, result.usage)

def _unique_sources(sources: list[Source]) -> list[Source]:
    seen: dict[str, Source] = {}
    for s in sources:
        seen.setdefault(s.url, s)
    return list(seen.values())[:MAX_SOURCES]

def _research_messages(conflict: OpenConflict, sources: list[Source]) -> list[dict[str, str]]:
    options = "\n".join(f"- {o}" for o in conflict.options)
    numbered = "\n".join(f"[{i}] {s.title} ({s.url})\n{s.snippet}" for i, s in enumerate(sources, start=1))
    user = f"Disagreement: {conflict.summary}\n\nOptions:\n{options}\n\nSources:\n{numbered}"
    return [{"role": "system", "content": RESEARCH_SYSTEM}, {"role": "user", "content": user}]

def _unknown_urls(summary: ResearchSummary, allowed: set[str]) -> str:
    unknown = [c.url for c in summary.citations if c.url not in allowed]
    return f"citations {unknown} are not in the sources" if unknown else ""


#votes
@dataclass
class Vote:
    user_id: str
    option: str
    domain_role: DomainRole | None

@dataclass
class Tally:
    winner: str | None #none when the vote is still tied
    totals: dict[str, int]
    decided_by: str #'vites' 'owner, 'domain', or 'tie'

def vote_weight(voter_role: DomainRole | None, domain: Domain) -> int:
    return 2 if voter_role == DOMAIN_OWNER[domain] else 1

def tally(options: list[str], votes: list[Vote], domain: Domain, owner_id: str) -> Tally:
    """Count weighted votes. A tie goes to the owner's choice, then to the option the domain-role voters backed."""
    latest = {v.user_id: v for v in votes if v.option in options} # a later vote replaces an earlier one
    totals = {o: 0 for o in options}
    for v in latest.values():
        totals[v.option] += vote_weight(v.domain_role, domain)

    best = max(totals.values(), default=0)
    leaders = [o for o in options if totals[o] == best and best > 0]
    if len(leaders) == 1:
        return Tally(leaders[0], totals, "votes")
    
    owner_vote = latest.get(owner_id)
    if owner_vote and owner_vote.option in leaders:
        return Tally(owner_vote.option, totals, "owner")
    
    domain_backed = {v.option for v in latest.values() if v.option in leaders and vote_weight(v.domain_role, domain) > 1}
    if len(domain_backed) == 1:
        return Tally(domain_backed.pop(), totals, "domain")
    return Tally(None, totals, "tie")