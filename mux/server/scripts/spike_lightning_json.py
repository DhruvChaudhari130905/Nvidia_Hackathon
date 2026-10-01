"""Spike: does Nemotron Lightning return valid coordinator JSON reliably?

Run from mux/server:
    .venv/bin/python -m scripts.spike_lightning_json --role lightning --reps 5
Pass: at least 95% of calls validate against SpikeAction. Otherwise the coordinator runs on Super.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from mux.agents.llm import ModelRole, TokenFactoryLLM


class SpikeAction(BaseModel):
    label: Literal["merge", "queue", "interrupt", "conflict", "chat"]
    rationale: str
    domain: Literal["ui", "architecture", "scope"] | None = None
    reply: str | None = None


SYSTEM = """You are the coordinator of a shared coding room. Several teammates steer one coding agent.
Label the NEW message with exactly one label:
- merge: fits the task in progress
- queue: new work that should become a new plan item
- interrupt: makes the work in progress wrong; stop and re-plan
- conflict: contradicts another pending or active instruction
- chat: a question or comment that needs no code change
Answer with JSON only:
{"label": "...", "rationale": "one sentence", "domain": "ui" | "architecture" | "scope" | null, "reply": "text for chat, else null"}"""

SCENARIOS: list[dict[str, Any]] = [
    {"current": "Build the RSVP form", "pending": [],
     "message": "Ana (Design): make the submit button purple", "expected": "merge"},
    {"current": "Build the RSVP form", "pending": [],
     "message": "Priya (PM): we also need an admin page that lists all RSVPs", "expected": "queue"},
    {"current": "Store RSVPs in SQLite, one table per event", "pending": [],
     "message": "Dan (Eng): wait, use one rsvps table with an event_id column, redo the schema", "expected": "interrupt"},
    {"current": "Build the RSVP form", "pending": ["Priya (PM): add Google login for RSVPs"],
     "message": "Dan (Eng): no auth, keep RSVPs anonymous", "expected": "conflict"},
    {"current": "Build the RSVP form", "pending": [],
     "message": "Priya (PM): what does the backend use for the database?", "expected": "chat"},
    {"current": "Build the event list page", "pending": [],
     "message": "Ana (Design): show each event date in bold", "expected": "merge"},
    {"current": "Build the event list page", "pending": [],
     "message": "Priya (PM): add a CSV export of RSVPs for organizers", "expected": "queue"},
    {"current": "Build the event list page", "pending": ["Ana (Design): keep everything on one page"],
     "message": "Priya (PM): split events and RSVPs into separate pages", "expected": "conflict"},
    {"current": "Build the event list page", "pending": [],
     "message": "Dan (Eng): nice, looks good so far", "expected": "chat"},
    {"current": "Build the event list as cards", "pending": [],
     "message": "Priya (PM): stop, the event list should be a calendar view, not cards", "expected": "interrupt"},
]

def render(sc: dict[str, Any]) -> str:
    pending = '\n'.join(f"- {p}" for p in sc["pending"]) or "(none)"
    return f"Task in progress: {sc['current']}\nPending messages:\n{pending}\nNEW message: {sc['message']}"

def lenient(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return text.strip()

def is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False
    
def validates(text: str) -> SpikeAction | None:
    try:
        return SpikeAction.model_validate_json(text)
    except ValidationError:
        return None
    
async def run_one(llm: TokenFactoryLLM, role: ModelRole, reasoning: bool | None,
                  sc: dict[str, Any], sem: asyncio.Semaphore) -> dict[str, Any]:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": render(sc)}]
    async with sem:
        start = time.perf_counter()
        try:
            reply = await llm.chat(role, messages, schema=SpikeAction, reasoning=reasoning, max_tokens=300)
        except Exception as e: #count api errors as failures, keep going
            return {"scenario": sc["message"], "expected": sc["expected"], "error": repr(e), "json":False, "schema":False, "lenient": False}
        seconds = time.perf_counter() - start

    strict = validates(reply.text)
    loose = strict or validates(lenient(reply.text))
    return{
        "scenario": sc["message"],
        "expected": sc["expected"],
        "text": reply.text,
        "json": is_json(reply.text),
        "schema": strict is not None,
        "lenient": loose is not None,
        "label": loose.label if loose else None,
        "seconds": round(seconds, 2),
        "tokens": reply.usage.total,
        "finish_reason": reply.finish_reason,
    }

def pct(results : list[dict[str, Any]], key: str) ->str:
    return f"{100 * sum(bool(r.get(key)) for r in results) / len(results):.0f}%"

async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=[r.value for r in ModelRole], default="lightning")
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--reasoning", choices=["on", "off", "default"], default="default")
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    role = ModelRole(args.role)
    reasoning = {"on": True, "off": False, "default": None}[args.reasoning]
    llm = TokenFactoryLLM()
    sem = asyncio.Semaphore(args.concurrency)

    jobs = [run_one(llm, role, reasoning, sc, sem) for sc in SCENARIOS for _ in range(args.reps)]
    results = await asyncio.gather(*jobs)

    for r in results:
        r["correct"] = r.get("label") == r.get("expected")
    ok = [r for r in results if "seconds" in r]
    secs = sorted(r["seconds"] for r in ok) or [0]

    print(f"model={role.value} reasoning={args.reasoning} calls={len(results)} api_errors={len(results) - len(ok)}")
    print(f"valid json    {pct(results, 'json')}")
    print(f"schema valid  {pct(results, 'schema')}   <- pass needs >= 95%")
    print(f"lenient valid {pct(results, 'lenient')}")
    print(f"label correct {pct(results, 'correct')}   (info only)")
    print(f"latency p50 {statistics.median(secs):.2f}s  p95 {secs[int(0.95 * (len(secs) - 1))]:.2f}s")
    if ok:
        print(f"avg tokens  {statistics.mean(r['tokens'] for r in ok):.0f}")
    passed = sum(r["schema"] for r in results) / len(results) >= 0.95
    print("PASS: coordinator on Lightning" if passed else "FAIL: coordinator on Super (or add lenient cleanup)")

    out = Path(__file__).parent / f"spike_results_{role.value}_{args.reasoning}.jsonl"
    out.write_text("\n".join(json.dumps(r) for r in results))
    print(f"raw results -> {out}")

if __name__ == "__main__":
    asyncio.run(main())
