# PRD — MUX: a multiplayer coding agent

> Eight people steering, one agent building. Google Docs for AI app-building.

| | |
|---|---|
| **Hackathon** | Nebius x NVIDIA Global AI Hackathon 2026 |
| **Track** | Coding and Agentic Engineering (primary) |
| **Bonus target** | Best Use of Tavily ($3,000) |
| **Team** | 4 students |
| **Submission deadline** | Oct 30, 2026, 10:00 AM PT (internal deadline: **Oct 28**) |
| **Status** | v2 — 2026-09-28. Updated with the architecture decisions (Q1–Q39) in [`../session-log/2026-09-28-architecture-grill.md`](../session-log/2026-09-28-architecture-grill.md). Technical detail lives in [`architecture.md`](architecture.md). |

**Name.** MUX is named after an 8:1 multiplexer: up to 8 people steering at once, and one agent building. The project was called Huddle until 2026-09-28.

---

## 1. Problem

AI coding agents (Cursor, Claude Code, Lovable, v0) are single-player. On a real product team, the PM, the designer, and the engineer all have opinions about what gets built, but only one person holds the keyboard. Everyone else shouts over a shoulder, pastes feedback into Slack, or waits for a screen share. The result:

- Non-engineers are locked out of the build loop and their intent gets lost in translation.
- The "driver" becomes a bottleneck and a lossy relay.
- Conflicting instructions ("add login" vs. "keep it anonymous") get resolved by whoever types last, with no record of why.

## 2. Solution

**MUX** is a shared agent session that a cross-functional team joins through a link, like a Google Doc. Everyone sees the agent think, code, and build in real time, and everyone can steer it at the same time.

Each room has **one agent** with two model roles:
- A fast Nemotron **coordinator** reads every message and decides *what* gets built. It labels each message merge, queue, interrupt, conflict, or chat, and it owns the plan.
- A strong Nemotron **coder** decides *how* to build the current task. It is the only AI that writes code.

Real conflicts become a **conflict card** with cited Tavily research attached, and the room votes on it. The team's roles (PM, Design, Eng) give each voice more weight in its own domain.

The agent builds **full-stack web apps** (a React frontend and a Hono backend with SQLite). Builds and tests run in **Nebius Token Factory Sandboxes**, and the live app runs in the browser. After every task the room saves a checkpoint, so the team can **rewind** to any point. People can also **edit the code by hand** alongside the agent. Output is a live preview plus export to GitHub.

MUX is built to be **token-efficient**: it targets at least 40% fewer tokens per finished task than a naive agent loop on the same models.

## 3. Target users

Primary: **cross-functional student and early-stage product teams** (PM + designer + engineer, 2–8 people) prototyping an app together, e.g. in hackathons, capstone projects, or startup ideation.

| Role | What they want from MUX |
|---|---|
| PM | Steer scope and features without waiting on an engineer; see a trail of why decisions were made |
| Designer | Directly shape the UI in the running prototype; own visual decisions |
| Engineer | Keep architecture sane; veto bad technical calls; edit code directly; export clean code to GitHub |
| Viewer (stakeholder, mentor) | Watch live without derailing the agent |

## 4. Hackathon alignment

Judging uses four equally weighted criteria. How MUX scores on each:

| Criterion | How MUX scores |
|---|---|
| **Technological Implementation** | Two Nemotron roles with distinct jobs on Token Factory; Token Factory Sandboxes for builds and tests, with a snapshot per checkpoint; full-stack apps running live in the browser; a measured token-efficiency result against a naive baseline; Tavily as a first-class tool |
| **Design** | Complete product: accounts, sharing, roles, live presence, plan approval, preview, editable code, conflict and question cards, timeline with rewind, export |
| **Potential Impact** | Real audience (cross-functional teams) with a real, observed pain (the one-driver bottleneck). Backed by a user test with 3+ real student teams and measured time-to-prototype |
| **Quality of Idea** | Multiplayer *steering* of one agent (not just a shared chat or co-editing) is non-obvious. Conflict resolution with role authority and evidence-backed voting is novel |

**Hard submission requirements checklist**
- [ ] Runs on Nebius Token Factory (models + Sandboxes) and Nebius AI Cloud (backend)
- [ ] Uses at least one NVIDIA open model (Nemotron 3 family)
- [ ] Public repo with OSS license (MIT) and README with setup instructions
- [ ] Working live demo URL
- [ ] Demo video under 3 minutes, on YouTube, with audio
- [ ] Project description and tool feedback write-up
- [ ] All work created during the submission period (Aug 26 – Oct 30, 2026)

## 5. Scope

### 5.1 MVP (must ship)

1. **Accounts and rooms**
   - Supabase Auth with Google and GitHub sign-in (basic scopes only).
   - Dashboard of the user's rooms; create a room from a prompt.
2. **Sharing (Google Docs model)**
   - Roles: **Owner / Editor / Viewer**.
   - Invite by email or share link; link access is *restricted* or *anyone with the link* (with a chosen permission).
   - On join, each member picks a **domain role**: PM, Design, or Eng.
3. **Live room UI**
   - Three columns: agent feed and composer (left), Preview and Code tabs (center), open cards and the plan (right). A timeline runs along the bottom, and the top bar holds presence, Share, Export, and the budget meter.
   - Presence (avatars, typing, active tab) over MUX's own WebSocket. No Liveblocks.
   - Live agent feed: narration, tool activity, build and test results, and each message with its coordinator label.
   - Steering composer; each message is tagged with author and role.
4. **Plan and approval**
   - The coordinator drafts a plan (a list of tasks) from the app description.
   - Editors can add, remove, reorder, and comment on tasks, live, before approval.
   - The owner approves once. Tasks added later do not need approval.
5. **Concurrent steering and coordinator**
   - Every message goes to the coordinator, one message at a time per room, so it can see other pending messages. It labels each message:
     - **merge**: fits the current task; given to the coder at its next turn boundary.
     - **queue**: new work; the coordinator adds it to the plan and picks its position.
     - **interrupt**: invalidates current work; the coder stops at its next turn boundary and re-plans.
     - **conflict**: contradicts another pending or active instruction; opens a conflict card.
     - **chat**: a question or comment; the coordinator replies, and the coder is not disturbed.
   - The coder never gets instructions mid-turn. Merges and interrupts apply at turn boundaries; vote results apply at task boundaries.
6. **Conflict cards**
   - Show the competing instructions, their authors and roles, and a short summary of the trade-off.
   - Tavily-backed evidence with citations (see 5.3).
   - Role-weighted vote: Design owns UI, Eng owns architecture and data, PM owns scope and features.
   - Editors vote. The vote closes when every editor has voted or after 60 seconds, and the owner can override at any time.
   - The coder skips the disputed task and keeps working on others.
   - The result is pinned in the room log and shown on the timeline.
7. **Question cards**
   - When the coder needs a decision, it posts a question card with options and a default answer (`ask_room`), then skips that task and keeps working on others.
   - Any editor or the owner can answer. After 5 minutes with no answer, the coder uses its default and says so.
8. **Coder agent**
   - Nemotron 3 Super by default; a task escalates to Ultra after 2 consecutive failed builds.
   - A fixed toolset with no free-form shell: `read_file`, `write_file`, `edit_file`, `list_files`, `delete_file`, `run_build`, `run_tests`, `web_search`, `ask_room`, `update_plan` (own task only), `finish_task`.
   - Generated apps use one fixed full-stack template: **React + Vite + Tailwind** frontend, **Hono** backend, **SQLite** database. Packages come only from an approved list baked into the starter image.
9. **Manual code editing**
   - Editors can edit files in the Code tab.
   - One person edits a file at a time; others see who is editing and a read-only view.
   - The coder is told about each manual edit at its next turn boundary. If the coder tries to change a file that changed since it read it, its edit fails and it re-reads first, so no one's work is silently overwritten.
   - Manual edits go into the next checkpoint and show on the timeline.
10. **Builds, checkpoints, and rewind**
    - Type-check, build, and tests run in a Token Factory Sandbox from a prebuilt starter image.
    - MUX's backend owns the project files. A checkpoint (file manifest + sandbox snapshot + room log) is saved after every finished task.
    - The owner and editors can **rewind** to any checkpoint. Files, plan, preview, and log revert instantly; later events are greyed out, not deleted, so the room can move forward again.
11. **Live preview**
    - The whole app (frontend and backend) runs in the browser in a **WebContainer**.
12. **Memory**
    - Each task starts with fresh context plus the latest room log.
    - A rolling log (about one page) is written after every task; vote results and owner overrides are pinned in it.
    - When a sitting ends (everyone gone for 30 minutes, or the owner clicks End session), the task logs are compacted into one day log that the next sitting reads.
13. **GitHub export**
    - Owner only. Export uses a separate "Connect GitHub" step that asks for repo permission; the token is stored encrypted on the server.
    - MUX's backend (not the AI) creates a new repository, or opens a PR against an existing one, from the current checkpoint.
14. **Guardrails**
    - At most 8 active steerers (Owner and Editors) per room; unlimited Viewers.
    - Rate limit: 1 steering message per user every 5 seconds.
    - Per-room budget of tokens and sandbox runs (default about 2M tokens), with a live meter. The room pauses at the cap until the owner raises it.
    - Only the Owner can export, delete, or change sharing. Teammate messages are instructions for the agent, never privilege escalation.
    - No AI component holds a GitHub token.
15. **Token efficiency**
    - Target: at least 40% fewer tokens per finished task than a naive agent loop on the same models, with the same or better build success rate.
    - Techniques are listed in [`architecture.md`](architecture.md) §8.

### 5.2 Deferred to week 4

- **Judge demo room.** Whether judges get their own room copy, scripted bot teammates, and how plan approval appears in it will be decided in week 4.

### 5.3 Stretch (only if weeks 1–3 land)

- **Fork a session:** fork the room at a checkpoint, explore with a subgroup, then propose a merge back.
- **Research mode:** a Tavily-grounded PM spec with competitor and market findings before building starts.
- Viewer suggestions promoted to steering messages by an editor.
- Real-time co-editing of one file by several people (CRDT).

### 5.4 Tavily usage (Best Use of Tavily)

1. **Coder tool (`web_search`):** looks up current library docs and API usage while coding, which reduces hallucinated APIs. Returns a short answer plus 2–3 snippets, cached per room.
2. **Conflict evidence (`research_conflict`):** when a conflict card opens, the coordinator writes 1–3 queries that frame the trade-off, runs them through Tavily, and attaches a short, **cited** summary before voting opens.

### 5.5 Out of scope

- Backends in languages other than TypeScript in generated apps.
- Mobile apps.
- Self-hosted models.
- Billing.

## 6. User flows

**6.1 Create, plan, and share**
1. The owner signs in with Google or GitHub and clicks *New room*.
2. They describe the app ("RSVP app for campus events, with a backend to store RSVPs") and pick a role (PM).
3. They click *Share*, invite teammates by email or copy the link, and set link access.
4. The coordinator drafts a plan. Editors edit it live, and the owner approves it.
5. The coder starts on task 1, and the feed begins streaming.

**6.2 Join and steer**
1. A teammate opens the link, signs in, and picks a role (Design).
2. Presence shows them in the room. They see the feed, the preview, and the plan.
3. They type "make it dark mode with a purple accent".
4. The coordinator labels it *merge*, and a chip appears on the message.
5. The coder picks it up at its next turn, and the preview reflects the change.

**6.3 Conflict**
1. The PM says "add Google login for RSVPs"; the engineer says "no auth, keep RSVPs anonymous".
2. The coordinator labels both *conflict* and opens a card with both positions and the role weighting.
3. Tavily evidence appears, with citations.
4. Editors vote, or the owner overrides. The result applies at the next task boundary and is pinned in the log.

**6.4 Question**
1. The coder reaches the checkout task and asks "Stripe test mode or a fake checkout?"
2. A question card appears, and the coder works on other tasks.
3. The owner picks an answer, and the coder continues with it.

**6.5 Manual edit**
1. The engineer opens `Hero.tsx` in the Code tab and fixes a heading. Others see "Dan is editing".
2. They save. Everyone sees the change, and the coder gets the diff at its next turn.

**6.6 Rewind**
1. The owner opens the timeline and clicks checkpoint 7.
2. Files, plan, preview, and log revert. Later work is greyed out, not deleted.

**6.7 Export**
1. The owner clicks *Export to GitHub*. The first time, MUX asks for GitHub repo permission.
2. They choose *new repo* or *PR to existing*, and get a link back.

## 7. Technical summary

See [`architecture.md`](architecture.md) for the full design. In short:

| Area | Decision |
|---|---|
| Backend | Python, FastAPI, one process on a Nebius CPU VM behind Caddy |
| Frontend | Next.js + TypeScript on Vercel |
| Room runtime | One in-memory room actor per room, applying changes one at a time; Postgres event log as the source of truth |
| Transport | REST for commands, WebSocket for events (resumable) and presence |
| Auth and data | Supabase Auth for login only; Supabase Postgres; all data through the backend |
| Coordinator | Nemotron 3.5 Lightning (Super for `create_plan`), fixed JSON output |
| Coder | Nemotron 3 Super, Ultra after 2 failed builds; hand-rolled agent loop |
| Builds and tests | Token Factory Sandboxes from a prebuilt starter image |
| Preview | WebContainer in the browser |
| Files | Owned by the backend: content-addressed blobs + manifests |
| Checkpoint | File manifest + sandbox snapshot UUID + room log, per task |

### 7.1 Model mapping (Nebius Token Factory)

| Job | Model | Why |
|---|---|---|
| Coordinator: labels, plan items, conflicts, replies | Nemotron 3.5 Lightning | Low latency on every message |
| Coordinator: first plan (`create_plan`) | Nemotron 3 Super | Plan quality matters and it runs once |
| Coder | Nemotron 3 Super, escalating to Ultra | Coding quality |
| Log compaction | Nemotron 3.5 Lightning | Short, structured output |

## 8. Success metrics and evals

| Metric | Target |
|---|---|
| Coordinator label accuracy on 50 hand-labeled concurrent-message scenarios | ≥ 85% |
| Time from plan approval to first preview | < 90 s |
| Build and test success rate across 20 scripted prompts | ≥ 80% |
| Steering latency (message sent to label visible) | < 2 s p50 |
| Tokens per finished task compared with a naive agent loop on the same models | ≥ 40% fewer |
| User test: 3+ real student teams | Faster time-to-prototype than a "one driver + Cursor" baseline, plus quotes for the README and video |

The eval harness lives in `mux/evals/`; results go in the README.

## 9. Demo video (under 3 minutes)

Draft beats. The final script is decided in week 4, together with the demo room.

| Time | Beat |
|---|---|
| 0:00–0:20 | The problem: one person drives the AI while the team shouts over their shoulder |
| 0:20–0:45 | The owner creates a MUX room; the coordinator drafts a plan; teammates edit it; the owner approves |
| 0:45–1:15 | Parallel steering: a style change merges, a new feature queues, and the preview updates live |
| 1:15–1:50 | Conflict card: PM vs Eng, with Tavily evidence and citations, a vote, and the result applied |
| 1:50–2:10 | A question card, and an engineer editing code by hand alongside the agent |
| 2:10–2:30 | Timeline rewind to a checkpoint; the preview reverts |
| 2:30–2:45 | Export to GitHub |
| 2:45–3:00 | Architecture and the token-efficiency result |

## 10. Team and timeline

| Person | Owns |
|---|---|
| P1 — Realtime frontend | `mux/web/`: room UI, presence, feed, preview (WebContainer), code editor, cards, timeline, sharing |
| P2 — Agent core | Coordinator, coder loop, tools, memory, token efficiency, evals |
| P3 — Infra | Sandboxes, starter image and template, file store, checkpoints and rewind, Nebius VM, Supabase, GitHub export |
| P4 — Product, design, and demo | UX design, Tavily integration and conflict evidence, user tests, README, video, submission; demo room in week 4 |

| Week | Dates | Goal |
|---|---|---|
| 1 | Sep 28 – Oct 4 | **Risk spikes by Oct 1** (see §11). **Walking skeleton:** auth, create/join a room, the coder building the starter template in a sandbox, events streamed to the browser, the app running in a WebContainer |
| 2 | Oct 5 – Oct 11 | Coordinator with merge/queue/interrupt/chat; plan drafting and approval; roles and permissions; presence; checkpoints per task |
| 3 | Oct 12 – Oct 18 | Conflict cards with Tavily evidence and voting; question cards; manual code editing; rewind; GitHub export |
| 4 | Oct 19 – Oct 25 | Token-efficiency work and evals, guardrails and budget, user tests with 3+ teams; **decide and build the demo room**; fork stretch only if on track |
| Final | Oct 26 – Oct 28 | Video, README, description, tool feedback; **submit Oct 28** (2-day buffer before Oct 30) |

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| WebContainers cannot run the full-stack template (Hono + SQLite) well | Spike by Oct 1. Fallback: expose a port from the Nebius sandbox if supported, or run each room's app in a container on the VM |
| Sandbox limits: 30 s default timeout, 8 KB output, 50 concurrent operations, network for `npm install` unconfirmed | Prebuilt starter image with packages installed; trimmed error output; ask Nebius on Discord to raise limits |
| Nemotron coder quality is too low for reliable builds | One fixed template stack; a short conventions sheet; build-and-fix loop; Ultra for failing tasks |
| Coordinator mislabels messages | Labeled eval set; label chips visible so users can correct them, and each correction becomes an eval example |
| Lightning's JSON output is unreliable | Spike by Oct 1; fall back to Super for the coordinator |
| Manual edits and coder edits collide | Version stamps on every read; stale edits fail; one human editor per file |
| Token target missed | Measure from week 2 against the naive baseline; the techniques in `architecture.md` §8 can be adopted one by one |
| WebSocket reliability on the VM | Reconnect and resume from the last event seq |
| Scope creep with 4 students | Demo decided in week 4; forking and research mode are strictly stretch; the week-1 skeleton is a hard gate |

## 12. Open questions

- Does WebContainers run Hono + SQLite from the starter template, and how fast does it boot? (Oct 1 spike.)
- Can a Nebius sandbox expose a port for a running app? If so, MUX may switch the preview to it.
- Does the sandbox have network access for `npm install`, and how long does a build take from the starter image?
- Does Token Factory support prompt caching, and a reasoning on/off switch for Nemotron?
- Are Lightning's JSON output and Super's tool calling reliable enough? Is Nemotron 3 Nano retired?
- Should a Nebius managed Postgres replace Supabase Postgres? Keep Supabase unless Nebius hosting is a scoring advantage.
