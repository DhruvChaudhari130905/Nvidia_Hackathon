# Session log — 2026-09-29 to 2026-09-30 — Backend plan and P-Agent-A start

**Goal:** Decide how to build the MUX backend from [`../source-of-truth/architecture.md`](../source-of-truth/architecture.md), split the work across the 4 backend people, and start P-Agent-A's code (the user owns P-Agent-A).
**Method:** A review of `source-of-truth/`, then a guided walkthrough. The user writes each file, and Claude explains, reviews, and tests it.
**Output:** `mux/server/mux/config.py`, `mux/server/mux/agents/llm.py`, `mux/server/scripts/spike_lightning_json.py`, and root `.gitignore` rules.

## 1. Backend approach

Build in this order: **contract first, spine second, real producers last.**

1. **Freeze the contracts.** Event types in `mux/server/mux/events/models.py`, REST command bodies, and the JSON Schema export for the frontend.
2. **Build the spine with fakes.** Event log, event bus, room actor, registry, WebSocket, and commands, run against `fake_llm` and `fake_sandbox`. Pass condition: a scripted room streams to the browser, and a reconnect with `?since=seq` loses nothing.
3. **Plug in real producers one at a time.** Files, coder loop, sandbox builds, coordinator, plan approval, checkpoints, conflicts with Tavily, questions, manual edits, rewind, export.

### Room actor rules (proposed, not yet in `architecture.md`)
- The actor loop never does slow work. It only validates, appends to Postgres, updates memory, and publishes. LLM, sandbox, and Tavily calls run in separate tasks that post results back to the mailbox.
- Mailbox items that need an answer carry an `asyncio.Future` (`await actor.ask(...)`), e.g. the coder's `edit_file` getting a new version or `stale`.
- The coordinator has its own serial queue per room, so a classify call does not block the actor.
- The coder has an explicit scheduler state (`idle | running | waiting_boundary | paused_budget | blocked_all_skipped`). When the coder is idle, vote results apply immediately.
- Seq numbers come from an in-memory counter in the actor. The `(room_id, seq)` primary key catches bugs.

### Gaps found in the current design (proposed fixes, to be decided as Q40+)
| Issue | Proposed fix |
|---|---|
| Rewind flips `events.active`, which breaks append-only and gets ambiguous on branches | Keep events immutable. Emit `room.rewound{checkpoint_id}` and compute the active set from the checkpoint tree |
| Rewind would also revert member joins, sharing, and budget | Split events into timeline events (files, plan, messages, cards, logs) and room-level events (membership, sharing, budget, export). Rewind only touches timeline events |
| Crash recovery "from latest checkpoint" misses members, open cards, locks, and budget | Replay from seq 0. Rooms have a few thousand events at most |
| Supabase pooler in transaction mode breaks asyncpg prepared statements | Use the direct or session connection string, or `statement_cache_size=0` |
| Browsers cannot set headers on a WebSocket | Send the JWT as the first socket message, not as a query parameter |
| Concurrent whole-plan `PATCH /plan` requests overwrite each other | Send plan operations (add, remove, move, rename) by item id |
| Sandbox output is truncated at 8 KB | Parse errors inside the sandbox and return short JSON |
| Locks can outlive their holder after a restart | Keep locks in memory only and clear them on actor rebuild |

## 2. Team split (4 backend people)

| Person | Owns |
|---|---|
| **P-DB** | `db/session.py`, `db/tables.py` (plus Alembic migrations), `events/log.py`, `files/store.py`, `files/manifest.py`, `checkpoints/checkpoint.py`, `checkpoints/rewind.py`, `sandbox/client.py`, `sandbox/runner.py`, `sandbox/errors.py`, `replay/fake_sandbox.py`, `tests/test_rewind.py` |
| **P-API** | `main.py`, `config.py`, `api/*`, `auth/*`, `events/models.py` (shared contract), `events/bus.py`, `rooms/*` (actor, registry, inbox, plan, locks, presence, sitting, budget), `integrations/github.py`, `scripts/export_schema.py`, `tests/test_actor.py`, `infra/Caddyfile`, `infra/vm-setup.sh` |
| **P-Agent-A (the user)** | `agents/llm.py` (shared with B), `agents/coordinator/*`, `integrations/tavily.py`, `memory/*`, `replay/fake_llm.py`, `tests/test_coordinator.py`, `evals/coordinator/` |
| **P-Agent-B** | `agents/coder/*` (loop, context, compaction, escalation, prompts, tools), `files/repo_map.py`, `templates/fullstack-starter/` with `CONVENTIONS.md`, `tests/test_coder_loop.py`, `tests/test_tools.py`, `evals/tokens/` |

All paths are under `mux/server/mux/` except `tests/`, `scripts/`, and `infra/` (under `mux/server/` or `mux/`), and `templates/` and `evals/` (under `mux/`).

**Interfaces to agree on day 1:** the `events/models.py` event types; `actor.post()`, `actor.ask()`, `actor.turn_boundary()`, and `actor.task_boundary()`; `log.append`, `log.read_since`, and `log.read_all`; `store.get/put` and `manifest.apply_edit` raising `Stale`; `runner.build()` and `runner.test()`; `llm.chat()`; `tavily.search()`; `task_log.write()`. Each person merges them as stubs that raise `NotImplementedError`.

## 3. P-Agent-A plan

Rule: the coordinator is pure. Data goes in and an action comes out. It never touches the actor, the database, or sockets.

| # | File(s) | Status |
|---|---|---|
| 1 | `mux/server/mux/config.py` (Agent-A fields), `mux/server/mux/agents/llm.py` | **Done**, tested offline. Real API test on the weekend |
| 2 | `mux/server/scripts/spike_lightning_json.py` | **Done**, tested offline. Real run on the weekend |
| 3 | `mux/server/mux/replay/fake_llm.py` | **Done** (Oct 1), offline test passes |
| 4 | `mux/server/mux/agents/coordinator/schema.py` | **Done** (Oct 1), offline test passes |
| 5 | `mux/server/mux/agents/coordinator/prompts.py`, `agent.py`, `mux/server/tests/test_coordinator.py` | **Done** (Oct 1) |
| 6 | `mux/server/mux/agents/coordinator/planner.py` | **Done** (Oct 1). Retry loop moved into a shared `ask_json` in `agent.py` |
| 7 | `mux/server/mux/integrations/tavily.py`, `mux/server/mux/agents/coordinator/conflicts.py`, `mux/server/tests/test_conflicts.py` | **Done** (Oct 1). 26 tests pass, pyright 0 errors |
| 8 | `mux/server/mux/memory/task_log.py`, `pins.py`, `day_log.py`, `mux/server/tests/test_memory.py` | **Done** (Oct 2). 36 tests pass, pyright 0 errors. See [`2026-10-01-agent-a-coordinator-and-memory.md`](2026-10-01-agent-a-coordinator-and-memory.md) |
| 9 | `mux/evals/coordinator/` | Next, needs API keys |

Check from `mux/server`: `.venv/bin/python -m pytest tests/test_conflicts.py tests/test_coordinator.py -q` and `uvx pyright --pythonpath .venv/bin/python mux tests/test_conflicts.py tests/test_coordinator.py`. `pytest`, `pytest-asyncio`, and `tavily-python` are installed in `.venv`.

Interfaces for teammates:
- P-API (actor): `Coordinator(llm).classify(RoomView, Message) -> Decision`, `create_plan(llm, description) -> PlanResult`, `insert_item(plan, AddPlanItem, status) -> list[PlanItem]`, `research_conflict(llm, TavilySearch(client), OpenConflict) -> Research`, `tally(options, votes, domain, owner_id) -> Tally`. API errors from the LLM propagate; model failures return `fallback=True`.
- P-Agent-B (coder): `TavilySearch` (one per room, shared `AsyncTavilyClient`) for `web_search`; `FakeLLM` for coder loop tests.

Editor note: the IDE saved stale buffers over fixed files several times (`schema.py` three times). Close or revert a tab after Claude edits its file.

## 4. What was built

### `mux/server/mux/config.py`
Pydantic settings read from environment variables or `mux/server/.env`: `token_factory_api_key`, `token_factory_base_url`, `model_lightning`, `model_super`, `model_ultra`, `tavily_api_key`. The file holds names only; the values live in `.env`.

### `mux/server/mux/agents/llm.py`
- `ModelRole` (LIGHTNING, SUPER, ULTRA). Callers name a role, not a model id.
- `Usage`, `ToolCall`, `LLMReply` dataclasses. `ToolCall.arguments` is `None` when the model sends invalid JSON, so the coder loop can ask it to retry.
- `LLM` Protocol, so `FakeLLM` can replace the real client in tests.
- `TokenFactoryLLM.chat(role, messages, *, tools, schema, reasoning, max_tokens, on_delta)`. It uses `json_schema` output with `strict: False` (the output is always validated with Pydantic afterwards), `reasoning` through `extra_body.chat_template_kwargs.enable_thinking` (unconfirmed), and streaming through `_stream` when `on_delta` is given.
- `llm.py` returns usage and does not track it. The actor adds it to the room budget.
- 17 bugs from hand-typing were fixed. An offline test with a fake OpenAI client passed in both modes, including a tool call split across stream chunks.

### `mux/server/scripts/spike_lightning_json.py`
- 10 room scenarios × `--reps` (default 5) = 50 calls, at most 5 at a time.
- Measures valid JSON, schema-valid, lenient-valid (after stripping code fences and `<think>` blocks), label accuracy (information only), p50 and p95 latency, and average tokens.
- Pass: at least 95% schema-valid, and the coordinator stays on Lightning. Otherwise it moves to Super.
- Flags: `--role lightning|super|ultra`, `--reasoning on|off|default`, `--concurrency`.
- Writes raw results to `mux/server/scripts/spike_results_<role>_<reasoning>.jsonl`.
- 10 bugs from hand-typing were fixed, plus one bug in Claude's original code: API errors counted as correct labels because `None == None`. An offline test with a fake LLM produced the expected percentages.

### Other
- A Python 3.12 venv at `mux/server/.venv` with `openai`, `pydantic`, and `pydantic-settings`.
- Root `.gitignore` now ignores `.env`, `.env.*` (except `.env.example`), and `.venv/` anywhere in the repo.

## 5. Concepts explained to the user
- Why API keys stay out of code (`.env`, `.gitignore`, `SecretStr`, never log settings, never put keys in prompts).
- Decorators: `@dataclass` and `@property`.
- `async def` and `await`: one process serving many rooms while it waits on the network.
- Type hints: editor checks, autocomplete, documentation, and fields in Pydantic and dataclasses.
- Every function in `llm.py`, plus `*` keyword-only arguments, `**kwargs`, and `field(default_factory=list)`.
- Spike concepts: `Literal`, `model_validate_json`, `asyncio.gather`, `asyncio.Semaphore`, `time.perf_counter`, `argparse`, and `if __name__ == "__main__"`.
- Lesson: the linter caught 1 of 10 spike bugs. Running the code against a fake caught the rest.

## 6. Weekend checklist (Oct 3–4)

The Oct 1 spike moved to the weekend. Until it runs, assume the coordinator runs on Super.

1. Create `mux/server/.env` from `mux/server/.env.example`. From the architecture session log: base URL `https://api.tokenfactory.nebius.com/v1/`, models `nvidia/Nemotron-3_5-Lightning`, `nvidia/nemotron-3-super-120b-a12b`, `nvidia/Nemotron-3-Ultra-550b-a55b`. Confirm the ids with `GET /v1/models`.
2. Smoke test `llm.py` with one call per role.
3. Test streaming (`on_delta=print`): tokens arrive live, and usage is not 0. Remove `stream_options` if Token Factory rejects it.
4. Test the reasoning switch with `--reasoning on` and `--reasoning off`.
5. Run the spike on Lightning, Lightning with reasoning off, and Super. Record the pass or fail result.
6. Run `classify` on 10 real scenarios. These seed the 50-scenario eval.
7. Share the results with the team, especially the streaming and reasoning answers for P-Agent-B.

## 7. Open items
- Tell the team the Oct 1 spike moved to the weekend.
- Tell P-API that Agent-A fields were added to `mux/server/mux/config.py`.
- Decide the gaps in section 1 as Q40+ and add them to `architecture.md`.
- Decide what happens to a vote tie that neither the owner nor a domain-role voter breaks. `tally` returns `winner=None, decided_by="tie"`. Proposal: the task stays `skipped_conflict` and the owner is asked to override.
- Fallback labels: a coordinator that fails twice queues the message; a planner that fails twice drafts a one-task plan. Confirm with the team.
- ~~`source-of-truth/design-theme.md` shows as deleted in `git status`.~~ Resolved Oct 2: Dhruv's commit `5d9d37c` deletes it on purpose.
- ~~Push blocked on repo permissions.~~ Resolved Oct 2: steps 1–8 pushed to `main` as `41baff2`.
