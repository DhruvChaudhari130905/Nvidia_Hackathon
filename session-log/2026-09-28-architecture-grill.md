# Session log — 2026-09-28 — Architecture grill for Huddle

**Status:** Draft, awaiting the user's approval. Q33 and the final summary are not yet confirmed.
**Goal:** Design the architecture for the agent, the backend, and the UI, based on [`../source-of-truth/prd.md`](../source-of-truth/prd.md).
**Method:** A structured grilling session (design tree, questions asked in rounds, each with a recommended answer). The questions were re-explained in plain language with a running example (Priya the PM and Dan the designer).
**Output (planned):** `architecture.md`, to be written after the user confirms.

## 1. Platform research (done during Round 1)

Sources: [Token Factory function calling](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling), [JSON mode](https://docs.tokenfactory.nebius.com/ai-models-inference/json), [rate limits](https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits), [Nemotron cookbook](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/README.md), [Sandboxes overview](https://docs.tokenfactory.nebius.com/sandboxes/overview), [Sandboxes branching](https://docs.tokenfactory.nebius.com/sandboxes/sdk/python_sdk/branching), [Sandpack Nodebox](https://sandpack.codesandbox.io/docs/advanced-usage/nodebox), [Tavily SDK](https://docs.tavily.com/sdk/python/reference), [Nebius endpoints](https://docs.nebius.com/serverless/endpoints/manage)

### Token Factory
- The API is OpenAI-compatible, at base URL `https://api.tokenfactory.nebius.com/v1/`.
- Models:
  - `nvidia/Nemotron-3_5-Lightning`
  - `nvidia/nemotron-3-super-120b-a12b`
  - `nvidia/Nemotron-3-Ultra-550b-a55b`
- Nemotron 3 Nano may be retired, with Lightning as its likely replacement. This is unconfirmed; check `GET /v1/models`.
- Super supports tool calling and structured output. Tool support on Lightning and Ultra is unverified.
- `response_format` supports `json_object` and `json_schema`.

### Sandboxes (ConTree, beta)
- This is **not a persistent dev box**. Each `run` boots a fresh microVM (about 2–5 s), runs one command, and exits.
- A run with `disposable=False` saves the result as a new image UUID. That UUID is the checkpoint, and branching or restoring means running from an old UUID.
- Limits: at most 50 concurrent operations, a 30 s default timeout, and 8 KB output truncation.
- Network access for `npm install` is unconfirmed, because the docs contradict each other.
- No preview ports are documented.

### Sandpack
- The `vite-react-ts` template runs in the browser on Nodebox.
- Tailwind through PostCSS in that template is unconfirmed; the Tailwind CDN play script is the safe option.
- The license is fine for an open-source hackathon demo.

### Tavily
- Basic search costs 1 credit and advanced search costs 2.
- The free tier is 1,000 credits a month.

### Hosting
- WebSocket support on Nebius Serverless endpoints is undocumented.
- A small CPU VM behind Caddy is the safe option.

## 2. Decisions

### Round 1: core runtime shape
| # | Question | Decision |
|---|---|---|
| Q1 | Backend process model | One FastAPI process on one VM. Each room is an in-memory **room actor** (an asyncio task) that owns the plan, the inbox, and the coder loop, and serializes all changes. Postgres is the durable event log, and the actor rehydrates from it after a crash. No Redis. |
| Q2 | Command vs event transport | The WebSocket carries server-to-browser events only and is resumable via `?since=seq`. Commands (steer, vote, rewind, and so on) are REST calls with the Supabase JWT, and they return the accepted event `seq`. |
| Q3 | Presence | **Drop Liveblocks** (this changes the PRD). Presence (avatars, typing, active tab) is sent as ephemeral messages over our own room WebSocket. |
| Q4 | Definition of "step" | Two levels. At a **turn boundary** (one LLM turn plus its tool calls), the inbox is drained: merges are injected and interrupts abort. At a **task boundary** (one plan item), a checkpoint is taken, a timeline node is added, and conflict resolutions are applied. |
| Q5 | Plan as a first-class object | Yes. The plan is a structured list (`[{id, title, status, owner_role?}]`) held by the room actor and shown in the UI. The coder changes it through an `update_plan` tool, and the actor validates each change. |
| Q6 | Coordinator concurrency | Messages are classified one at a time per room through the actor, so each classification sees the other pending messages and can detect conflicts. A debounce batch is a fallback only if evals show misses. |
| Q7 | File state source of truth | The **backend owns the files**: a content-addressed file store, with a manifest of path-to-hash. The sandbox borrows the files for runs. This is effectively forced by the run-per-command sandbox model. |
| Q8 | Shared event schema | Pydantic models, exported to JSON Schema, with TypeScript types generated in CI. The frontend is a pure reducer over events. |
| Q9 | Repo layout | A monorepo with `web/`, `server/`, `packages/schema/`, `evals/`, and `templates/react-vite-tailwind/`, plus a **fake LLM and fake sandbox replay mode** so the UI can be built before the agent works. |
| Q10 | Room UI layout | Three columns: agent feed and composer on the left, Preview/Code tabs in the center, and Plan/Queue and conflict cards on the right. A timeline scrubber runs along the bottom, and the top bar holds presence, share, and the budget meter. Conflict cards also appear as a banner over the feed. |

### Round 2: agent, models, sandbox, hosting
| # | Question | Decision |
|---|---|---|
| Q11 | Agent framework | A hand-rolled loop (about 300 lines of Python) using the OpenAI client pointed at Token Factory. Frameworks fight the custom pause and interrupt points. |
| Q12 | Coordinator model | Nemotron 3.5 Lightning with a fixed JSON schema output, falling back to Super if the JSON proves unreliable. |
| Q13 | Coder model | Super by default. A task escalates to Ultra after 2 consecutive failed builds on it. |
| Q14 | npm packages | One pre-built **starter image** with React, Vite, Tailwind, and an **approved package list** already installed. No runtime `npm install`. |
| Q15 | Coder tools | A fixed toolset, with no free-form shell: `read_file`, `write_file`, `edit_file`, `list_files`, `delete_file`, `run_build` (type-check plus build in the sandbox), `web_search` (Tavily), `update_plan`, and `finish_task`. |
| Q16 | Checkpoint | At each task boundary, the checkpoint stores the file manifest **plus** the Nebius snapshot UUID of the successful build run, shown in the timeline as "built on Nebius". Rewind uses the manifest, so it is instant. |
| Q17 | Tailwind in the preview | The project files keep the normal Tailwind config, so exported code is clean. The Sandpack preview injects the Tailwind CDN script. |
| Q18 | Hosting | A Nebius CPU VM running uvicorn behind Caddy, which handles TLS and WebSocket upgrades. Not Serverless. |
| Q19 | Open conflict behavior | The coder skips the disputed task and keeps working on others, or waits if none are left. The vote closes when all editors have voted or after 60 s. It uses role-weighted majority, and the owner can override at any time. |
| Q20 | Browser database access | The browser uses Supabase for login only. All data goes through the backend, so all permission rules live in one place, in Python. |

### Round 3: rewind, demo, budget, memory, export, spikes
| # | Question | Decision |
|---|---|---|
| Q21 | Rewind | Files, the plan, and the preview revert instantly. Later events are greyed out, not deleted, so the room can rewind forward again. A running coder stops at its next turn boundary. Queued messages are kept and re-classified. The owner and editors can rewind. |
| Q22 | Demo bots | Each judge gets their **own copy** of the demo room, started from a half-built checkpoint and auto-deleted after 30 min. Bot messages are **pre-written with fixed timing** and sent through the same path as human messages. |
| Q23 | Budget meter | Counts tokens (from the API usage fields) plus sandbox runs. Defaults to about 2M tokens per room, with a smaller cap for demo copies. The room pauses at the cap until the owner raises it. |
| Q24 | Build start | **Changed by the user:** the agent shows the plan and to-do list and **waits for approval** before it starts building (see Q28). |
| Q25 | Coder memory | **Changed by the user:** each task starts with fresh context (rules, plan, file list, relevant files, and merged messages) **plus the session log from the previous session only** (see Q30, Q31, and the day log below). |
| Q26 | GitHub export auth | Sign-in asks for basic scopes only. Export triggers a separate "Connect GitHub" step for repo permission, and the token is stored encrypted on the server. This also works for users who signed in with Google. |
| Q27 | Week-1 risk spikes (due Oct 1) | P2: Lightning JSON reliability and Super tool calling. P3: sandbox `npm install`/network access and build time from the starter image. P1: Sandpack renders the starter app with the Tailwind CDN. P3: WebSockets through Caddy on the Nebius VM. Fallbacks: Super as coordinator or JSON-in-text; bake packages into the image offline and build only at task end; WebContainers; SSE. |

### Round 4: follow-ups from the user's changes
| # | Question | Decision |
|---|---|---|
| Q28 | Who approves the plan | The owner approves. Editors can edit the plan (add, remove, reorder, comment) before approval, and their edits appear live. |
| Q29 | Approval for tasks added mid-build | No. Approval happens once, at the start. After that, the coordinator handles merge, queue, and conflict, so the owner does not become a bottleneck again. |
| Q30 | What a "session" is | Both a task and a sitting use the same mechanism. A log is written at the end of every task, and a returning room reads the latest log. |
| Q31 | Preventing memory loss | A **rolling** log: each new log carries forward what still matters from the previous one (key decisions, vote results, conventions), stays capped at about 1 page, and **pins** vote results and owner overrides. |
| Q32 | Plan approval in the demo room | The judge owns their copy. Scripted bot tasks flow normally under Q29, and plan approval is shown in the "New room" flow and in the video. |

**Day log (the user's addition, agreed with two corrections).** When a sitting ends, the task logs are compacted into one **day log**, and the next sitting reads only the day log.
- Correction 1: the day log *summarizes the current state* rather than concatenating task logs. It covers what the app is, key decisions and vote results, conventions, and unfinished work, in about 1 page. It also rolls from day to day.
- Correction 2: a sitting "ends" when all members have been gone for 30 min, or when the owner clicks **End session**.

| # | Question | Decision |
|---|---|---|
| Q33 | Logs and rewind | *Pending confirmation.* Recommended: each log is stored alongside its checkpoint, so a rewind also restores the log from that moment and the agent does not remember undone work. |

### Round 5: tools, full-stack output, manual editing, tokens
The user made three scope changes before this round:
- **Generated apps are full-stack** (frontend and backend), not front-end only.
- **Manual code editing is in the MVP**, not a stretch goal.
- **The demo is deferred.** Q22 (demo room copies and scripted bots) and Q32 (plan approval in the demo) are on hold until week 4. They are not deleted.

| # | Question | Decision |
|---|---|---|
| Q34 | Coder needs an answer from the team | Approved. An `ask_room` tool: the coder posts a question card with options and a default answer, skips that task, and keeps working on others. Any editor or the owner can answer, and the answer reaches the coder as a merge and is pinned in the log. After 5 minutes with no answer, the coder uses its default and says so in the feed. |
| Q35 | Who owns the plan | Approved. The coordinator decides what gets built and the coder decides how. `create_plan` (coordinator, runs on Super) drafts the first task list for editors to edit and the owner to approve. `add_plan_item` (coordinator) adds queued requests and picks their position. The coder's `update_plan` is narrowed to marking its own task's status or splitting its own task. The room actor validates every plan change. |
| Q36 | How full-stack apps run and preview | Approved: option A. Generated apps use one fixed template: React + Vite + Tailwind, a Hono backend, and SQLite (browser-compatible build). The whole app runs in the browser in a WebContainer for the live preview. The Nebius sandbox still runs type-check, build, and tests. The web app sends COOP/COEP headers. Option B (a port exposed from the Nebius sandbox) is tested in the Oct 1 spikes, and Huddle switches to it if it works. |
| Q37 | People and the coder editing the same files | Approved. The Code tab is editable for editors. Saves go over REST to the room actor and stream to everyone. The coder is told about the edit at its next turn boundary. Every file read returns a version stamp, and `edit_file` fails with "file changed, re-read first" if the file changed since it was read. One person edits a file at a time (soft lock), and others see it read-only. Manual edits go into the next checkpoint, and the timeline shows a manual-edit marker. |
| Q38 | Token efficiency | Approved. Goal: at least 40% fewer tokens per finished task than a naive agent loop on the same models, with the same or better build success rate. Techniques: fresh context per task; stubbing already-used tool results after each turn; `read_file` with line ranges; a compact repo map from `list_files`; search-and-replace edits; build and test output trimmed to 5 deduplicated errors; short Tavily results cached per room; the starter template and a short conventions sheet; the right model per job; reasoning off for simple edits; a stable prompt prefix for caching; turn limits and loop detection; a coordinator that never sees file contents. Measured in `evals/tokens` against a naive baseline, and against Aider or OpenHands if time allows. The budget meter in the UI stays as it is (no comparison shown). |
| Q39 | `run_tests` tool | Approved. The coder gets `run_tests`, which runs the backend's tests in the sandbox. |

**Final tool list.**
- Coder: `read_file`, `write_file`, `edit_file`, `list_files`, `delete_file`, `run_build`, `run_tests`, `web_search`, `ask_room`, `update_plan` (narrow), `finish_task`.
- Coordinator: `classify`, `create_plan`, `add_plan_item`, `open_conflict`, `research_conflict`, `reply`. These can be implemented as fields in the coordinator's JSON output rather than real tool calls. The room actor carries each one out after validating it.

**Other decisions this round.**
- **Name:** the project is renamed from Huddle to **MUX**, after an 8:1 multiplexer: up to 8 people steering (the existing steerer cap), one agent building. Earlier sections of this log keep the old name.
- **Language split:** Huddle's backend is Python and its frontend is TypeScript (Next.js on Vercel). Apps that Huddle generates are TypeScript.
- **Theme:** GitHub Dark, recorded in [`../source-of-truth/design-theme.md`](../source-of-truth/design-theme.md).
- **Repo skeleton:** created at [`../mux/`](../mux/), with one file per responsibility. Every file holds only a description, and nothing is implemented yet.

## 3. Changes to the PRD implied by these decisions
- §5.1.3 and §7.3: remove Liveblocks, because presence goes over our own WebSocket.
- §7.2: the coordinator and conflict summary use Nemotron 3.5 Lightning instead of Nano. The coder escalates to Ultra after 2 failed builds.
- §5.1.6: the coder's tools are a fixed set with no free-form shell, and packages come only from the approved list.
- §5.1.7 and §7.1: a checkpoint is the backend's file manifest plus the Nebius snapshot UUID of the build. Checkpoints happen per task, not per LLM turn.
- §6.1: add a plan approval step (owner approves, editors can edit) before building starts.
- §7.4: new tables or fields are needed: a file blob store, checkpoint manifests, task and day logs tied to checkpoints, the plan, and an encrypted GitHub token.
- §5.1.6, §5.4, §11: generated apps are full-stack (React + Vite + Tailwind, Hono, SQLite). Remove "full-stack apps" from out of scope.
- §5.1.8: the preview runs the whole app in a WebContainer. Sandpack and static serving are no longer the plan.
- §5.1.3, §5.2: manual code editing moves from stretch into the MVP, with soft locks and version checks.
- §5.1.6: the coder tool list becomes the Round 5 list, including `run_tests` and `ask_room`. The coordinator gets `create_plan`, `add_plan_item`, `open_conflict`, `research_conflict`, and `reply`.
- §5.1.9: the GitHub token from sign-in is no longer reused for export. Export has its own Connect GitHub step.
- §5.1.10, §6.6, §9: the demo room and bots are deferred to week 4.
- §8: add the metric "tokens per finished task, at least 40% below a naive agent loop".
- Everywhere: rename Huddle to MUX.

## 4. Notable reasoning
- **Why the backend owns the files:** sandboxes are run-per-command with no live filesystem. Owning the files also makes rewind instant and independent of sandbox latency.
- **Why the coordinator runs serially:** classifying messages in parallel can't detect conflicts, since each call never sees the other message.
- **Why there is only one approval gate:** per-task approval would recreate the one-driver bottleneck that Huddle exists to remove.
- **Why the logs roll:** "read only the latest log" would otherwise drop decisions after two hops, and the agent could re-add something the team voted down.

## 5. Next steps
1. The user approves this log and confirms Q33 and the full summary.
2. Done 2026-09-28: [`../source-of-truth/architecture.md`](../source-of-truth/architecture.md).
3. Done 2026-09-28: `prd.md` updated to v2 with the changes in §3.
4. Run the week-1 risk spikes by Oct 1. Added in Round 5: WebContainers running the full-stack template, a port exposed from the Nebius sandbox (option B), and whether Token Factory supports prompt caching and a reasoning toggle for Nemotron.
