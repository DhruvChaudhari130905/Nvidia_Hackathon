# Session log — 2026-10-01 to 2026-10-02 — P-Agent-A: coordinator, Tavily, and memory

**Goal:** Finish the offline part of P-Agent-A's plan (steps 3–8 in [`2026-09-30-backend-plan-and-agent-a.md`](2026-09-30-backend-plan-and-agent-a.md)).
**Method:** Guided walkthrough. Claude drafts and tests each file in a scratch copy, explains it, the user types it, and Claude reviews it with pytest and pyright.
**Result:** Steps 3–8 done. 36 tests pass and pyright reports 0 errors. Everything runs offline against `FakeLLM` and a fake Tavily client. No real API call has been made yet.

## 1. What was built

All paths are under `mux/server/`.

| Step | File | What it does |
|---|---|---|
| 3 | `mux/replay/fake_llm.py` | `FakeLLM`: same `chat()` as `TokenFactoryLLM`, replays scripted replies (string, Pydantic model, `LLMReply`, or exception), records every call in `calls`, streams text in chunks through `on_delta`, and fails loudly when the script runs out |
| 4 | `mux/agents/coordinator/schema.py` | Pydantic output shapes: `CoordinatorAction` (label plus the fields each label needs, checked by a model validator; fields of other labels are dropped), `PlanDraft`, `ResearchSummary`. Shared literals `Label`, `Domain`, `DomainRole` |
| 5 | `mux/agents/coordinator/prompts.py` | Input types `PlanItem`, `Message`, `RoomView` (no file contents by design), the fixed system prompt, and `build_messages` |
| 5 | `mux/agents/coordinator/agent.py` | `Coordinator.classify(room, message) -> Decision`. Shared `ask_json`: call, strip `<think>` blocks and code fences, validate, run an extra check, and retry once with the error shown to the model. `unknown_ids` rejects made-up plan or message ids. Fallback after two failures: queue the message |
| 6 | `mux/agents/coordinator/planner.py` | `create_plan(llm, description) -> PlanResult` on Super, ids `t1..tN` assigned by code, status `draft`. Fallback: a one-task plan. `insert_item` places a queued item after `after_task_id` or at the end; `next_task_id` never reuses an id |
| 7 | `mux/integrations/tavily.py` | `TavilySearch`: one per room, with a per-room cache, snippets cut to 300 characters, and our own `Source`/`SearchResult` types. `WebSearch` Protocol for fakes. Shared with P-Agent-B's `web_search` tool |
| 7 | `mux/agents/coordinator/conflicts.py` | `research_conflict`: 1–3 queries in parallel (a failed query is skipped), sources de-duplicated by URL, cited neutral summary, and citations checked against the real Tavily URLs. Fallback: Tavily's own answers plus the first 3 sources. `tally`: weighted votes (domain role counts 2), ties go to the owner, then to the domain-role voter, else `winner=None` |
| 8 | `mux/memory/pins.py` | Frozen `Pin`; `pin_vote` (from a `Tally`), `pin_override`; `merge_pins` keeps one pin per conflict, and a later pin replaces an earlier one in place |
| 8 | `mux/memory/task_log.py` | `write_task_log` rolls the previous log forward into a `LogDraft` (app, changed, open threads, conventions), capped at 2400 characters. Pins are added by code after the model's text, and the model never sees them. Fallback: the old log plus the raw changes. Shared `write_log` and `render_log` |
| 8 | `mux/memory/day_log.py` | `write_day_log` compacts the previous day log and today's task logs into one log and merges all pins. No tasks means no model call. Fallback: the latest task log |
| — | `tests/test_coordinator.py`, `tests/test_conflicts.py`, `tests/test_memory.py` | 36 tests covering success, retry, fallback, made-up ids and URLs, caching, vote weights and ties, and log rolling |

The `spike_lightning_json.py` typing fixes were applied again (they had been lost), and the script was checked against `FakeLLM`.

`pytest`, `pytest-asyncio`, and `tavily-python` were installed in `mux/server/.venv`.

## 2. Decisions made in this session

- The coordinator, planner, conflict research, and logs all default to **Super** until the Lightning spike passes. Each takes a `role` argument, so switching is a one-line change.
- LLM API errors are not caught in Agent-A code. `llm.py` already retries 3 times, and the actor decides what to do next. Bad model answers are retried once, then a safe fallback is used and `fallback=True` is returned.
- The model never picks ids (plan ids come from code) and never sees pins. Ids and URLs that it returns are checked against real data.
- Logs are structured JSON (`LogDraft`) rendered to text by code, not free text.

## 3. Interfaces for teammates

- **P-API (actor):** `Coordinator(llm).classify(RoomView, Message) -> Decision`; `create_plan(llm, description) -> PlanResult`; `insert_item(plan, AddPlanItem, status) -> list[PlanItem]`; `research_conflict(llm, TavilySearch(client), OpenConflict) -> Research`; `tally(options, votes, domain, owner_id) -> Tally`; `pin_vote` / `pin_override`; `write_task_log(llm, previous, task, changes, plan, new_pins) -> LogResult` at each task boundary; `write_day_log(llm, previous_day, task_logs) -> LogResult` at end of sitting. The actor owns the 60-second vote timer and the owner override.
- **P-DB:** store `Log.draft` (JSON) and `Log.pins` (JSON list) in the `logs` table with the checkpoint, so a rewind restores the log.
- **P-Agent-B:** `TavilySearch` for `web_search`; `FakeLLM` for coder loop tests; `Log.body` is the room log for the coder's context.

## 4. How to check

From `mux/server`:

```
.venv/bin/python -m pytest tests/test_memory.py tests/test_conflicts.py tests/test_coordinator.py -q
uvx pyright --pythonpath .venv/bin/python mux tests/test_memory.py tests/test_conflicts.py tests/test_coordinator.py
```

## 5. Lessons

- The IDE saved stale buffers over fixed files several times (`schema.py` three times, also `fake_llm.py` and the spike script). VS Code only reloads a tab from disk when it has no unsaved edits. Close or revert a tab after Claude edits its file.
- Most typing bugs were renames, missing commas, and wrong indentation (functions indented into a class, a test nested inside another test). A syntax error hides every later error, so fix the first error and run the checks again.
- Pyright found bugs the tests missed (`None` access in tests), and the tests found bugs pyright cannot see (a stray space in a string, a wrong slice index).

## 6. Next

1. Weekend (Oct 3–4): fill `mux/server/.env`, smoke-test `llm.py` (one call per role, streaming, reasoning switch), run the Lightning spike, run `classify` on 10 real scenarios.
2. Step 9: `mux/evals/coordinator/`, 50 scenarios, label accuracy at least 85%.
3. Team: share the interfaces above; decide the unbreakable vote tie and the fallback rules (open items in the 2026-09-30 log).
