# Session log — 2026-09-27 — Ideation grill for Huddle

**Goal:** Ideate a multiplayer ("Google Docs–style") agent for the Nebius x NVIDIA Global AI Hackathon 2026, then produce `prd.md`.
**Method:** A structured grilling session (design tree, questions asked in rounds, each with a recommended answer).
**Output:** [`../prd.md`](../prd.md)

## 1. Hackathon research (done before questioning)

Sources: [Devpost overview](https://nebiusglobalaihackathon.devpost.com/), [Devpost rules](https://nebiusglobalaihackathon.devpost.com/rules), [Nebius Sandboxes docs](https://docs.tokenfactory.nebius.com/sandboxes/overview), [Nemotron on Token Factory](https://nebius.com/services/token-factory/nemotron)

- Submission window: Aug 26 – **Oct 30, 2026, 10:00 AM PT**. Judging: Dec 1–15. Winners announced around Jan 11, 2027.
- Requirements:
  - Runs on Nebius Token Factory or AI Cloud.
  - Uses at least one NVIDIA open model.
  - Public repo with an OSS license and a README.
  - Working demo URL.
  - Video under 3 minutes on YouTube.
  - Tool feedback write-up.
  - Project new, or significantly updated, during the window.
- Judging: 4 equally weighted criteria. Technological Implementation, Design, Potential Impact, Quality of Idea.
- Tracks: Coding & Agentic Engineering, Best Apps & Agents, Personal AI, Physical AI. Each track winner gets a Jetson Orin Nano.
- Prizes:
  - Overall: $20k / $10k / $6k.
  - Best Use of Tavily: $3k.
  - City winners: $500.
  - Feedback award: $100.
  - A project can win one Overall award, **or** one Track award plus one Bonus award.
- Sponsor tech: Token Factory (Nemotron 3 Nano / Super / Ultra / 3.5-Lightning), Token Factory Sandboxes (beta, Git-like branching, Python SDK / CLI / MCP / REST, 50 concurrent operations, no documented preview ports), Tavily, Nebius Serverless, NemoClaw, OpenShell, Hermes Agent.
- Scale: about 12.6k participants and 18 judges (NVIDIA, Nebius, Tavily).

## 2. Decisions

### Round 1
| # | Question | Decision |
|---|---|---|
| Q1 | Track | Coding & Agentic Engineering |
| Q2 | Who is in the room | Cross-functional team (PM, designer, engineer) |
| Q3 | Core multiplayer mechanic | Concurrent steering (hero) + live presence; forking as a stretch goal |
| Q4 | Team | 4 people, students |
| Q5 | Target the Tavily bonus | Yes |

### Round 2
Research between rounds: Sandboxes support Git-like branching (so forking is cheap), but no preview ports are documented.

| # | Question | Decision |
|---|---|---|
| Q6 | What the agent builds | Web apps and prototypes from scratch with a live preview, plus a GitHub export |
| Q7 | Conflict model | A coordinator agent (fast Nemotron) classifies messages as merge, queue, interrupt, or conflict. Conflicts go to a vote, and the owner can override. The coder applies changes only at step boundaries. Baton/lock mode is the fallback |
| Q8 | Roles and authority | Role-aware (PM / Design / Eng get more weight in their own domain); the owner can override |
| Q9 | Forking | Stretch goal; checkpoint every step from day one, and rewind is in the MVP |
| Q10 | Stack | Next.js (TypeScript) frontend + Python FastAPI backend (the Sandboxes SDK is Python) |
| Q11 | Realtime | Our own WebSocket event log as the source of truth + Liveblocks for presence |

### Round 3
| # | Question | Decision |
|---|---|---|
| Q12 | Preview hosting | Generated apps are front-end only (React + Vite + Tailwind). Preview renders in the browser via Sandpack/WebContainers; fallback is static output built in the sandbox and served by the backend |
| Q13 | Tavily role | A coder tool for docs, plus cited evidence on conflict cards. Research mode is a stretch goal |
| Q14 | Rooms and auth | **Full accounts** (the user chose this over the recommended no-account link sharing) |
| Q15 | Deployment | Frontend on Vercel; backend on a Nebius AI Cloud VM; Postgres |
| Q16 | Demo scenario | A 3-person team builds an app live, with a scripted sequence: join, parallel steering, conflict + Tavily + vote, rewind, export |
| Q17 | Team split | P1 realtime frontend, P2 agent core, P3 infra, P4 product/design/demo. 4-week plan; internal deadline Oct 28 |
| Q18 | Name | Huddle |

### Round 4 (follow-ups from the full-accounts decision)
| # | Question | Decision |
|---|---|---|
| Q19 | Auth provider | Supabase Auth (Google + GitHub OAuth); Supabase also hosts Postgres. The GitHub token is reused for export |
| Q20 | Judge friction | One-click OAuth + a "Try demo room" with 2 scripted bot teammates |
| Q21 | Sharing permissions | Owner / Editor / Viewer; invite by email or link; link access restricted or anyone-with-link |
| Q22 | Guardrails | At most 8 steerers per room, 1 message per 5 s per user, a per-room budget meter, and owner-only export/delete/sharing |
| Q23 | Metrics and evals | Coordinator triage accuracy on 50 labeled scenarios, time to first preview, build success rate, and a user test with 3+ student teams |

The user confirmed a shared understanding after Round 4, and the PRD was written.

## 3. Notable reasoning

- **Why the coding track with a non-engineer audience:** the agent writes, runs, and tests code in Token Factory Sandboxes (the track's showcase feature), while the multiplayer story brings PMs and designers into that loop. This is the non-obvious angle for the Quality of Idea criterion.
- **Why two Nemotron tiers:** the coordinator must be fast on every message, while the coder needs quality. Giving each tier a distinct job strengthens the Technological Implementation criterion.
- **Why demo bots:** judges almost always test alone, and without bot teammates a solo judge would see no multiplayer at all.
- **Why front-end-only generated apps:** Sandboxes have no documented preview ports; in-browser preview removes that infrastructure risk.

## 4. Open items carried into the PRD

- Verify that Token Factory supports streaming and tool-calling for Nemotron 3 Super.
- Measure Sandboxes checkpoint/restore latency (it affects the rewind UX).
- Decide between a Nebius managed Postgres and Supabase Postgres.

## 5. Next steps

- Week 1 (Sep 28 – Oct 4): walking skeleton, as defined in PRD §10.
- Set up the repo (MIT license), Supabase project, Token Factory keys, Tavily key, and Nebius VM.
- Ask Nebius on Discord about Sandboxes beta limits and preview/port support.
