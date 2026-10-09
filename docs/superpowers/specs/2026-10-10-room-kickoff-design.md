# Room kickoff ("Plan it with me"): design

**Date:** 2026-10-10 · **Status:** approved in conversation, awaiting spec review

## Problem

Every room's Decisions & plan panel looks the same: rooms start with an empty plan that only grows from chat
messages, and nothing reads the room's idea or (for imports) its code. The plan in older rooms came from a
since-removed step that planned from the description alone, so it ignored the project.

## Goal

When a room is created from an idea or an imported project, MUX works out a plan with the team the way
Superpowers' brainstorming skill does: understand the project, ask a few multiple-choice questions one at a
time, then draft a plan from the answers for the owner to approve. (The skill itself can't run in MUX: it
is written for Claude Code's tools. This is the same process built from MUX's own pieces.)

## Decisions

| Question | Decision |
|---|---|
| When | Opt-in per room with a "Plan it with me" switch in the create and import dialogs, on by default. |
| Who triggers it | The web app calls `POST /rooms/{id}/kickoff` (owner) right after creating the room, or, for imports, after the imported files are saved to the room. |
| Understand | If the room has files, a read-only task (`kind: "understand"`, already approved) reads them and finishes with a summary. With no files, the room's description is the summary. |
| Clarify | The coordinator asks 2–3 multiple-choice questions, one at a time, as the existing question cards. Anyone in the room can answer; an unanswered card takes its default when it expires (the room's question timeout). |
| Plan | The planner drafts 3–8 tasks from the description, the summary and the answers, as `draft` items. The owner approves with **Approve plan**, as today. If the plan already has items, the new ones are appended as drafts. |
| Visibility | Each step posts a `kickoff.step` notice to the feed: "Reading your project…", "Question 1 of 3", "Plan drafted from your answers — approve it to start". |
| No model | `POST /kickoff` answers 409 "This room has no AI model"; nothing is posted. |

## Flow

```
POST /rooms/{id}/kickoff ──► actor.request_kickoff() ──► event kickoff_requested
                                                              │ (runtime, as a background task)
        files? ──yes──► add "Understand the project" task (kind=understand, todo) ──► coder (read-only)
          │                 └─ summary = its finish_task text (waits for the task to end)
          no ──► summary = room description
        coordinator: KickoffQuestions (2–3 × {question, options 2–4, default}) from description + summary
        for each question: ask_and_wait(question, options, default, task_id=None)   (one at a time)
        planner: create_plan(description, context = summary + Q&A) ──► actor.add_plan_item(..., "draft") × n
        feed: kickoff.step at each stage
```

## Components

### API (`api/rooms.py`)

- `RoomCreateRequest` is unchanged; the web app calls the new endpoint itself, so imports can wait for their files.
- `POST /rooms/{id}/kickoff` (owner) → `{"accepted": true}`; 409 if the room has no model
  (`runtime.llm.available()` is False) or a kickoff is already running for the room.

### Room actor and events

- `KickoffRequestedEvent(requested_by)` (`kickoff_requested`); wire type `kickoff.requested` `{}`.
- `actor.request_kickoff(user_id)` records it. The runtime handles it; a kickoff running during a server
  restart is not resumed (the owner can press **Plan it with me** again from the plan's empty state).

### Runtime (`rooms/runtime.py`)

- `_kickoff()` runs as one background task per room (`self._kickoff_task`); a second request while it runs is refused by the API.
- **Understand:** when `actor.list_files()` is non-empty, add `{"title": "Understand the project", "status": "todo", "kind": "understand"}` and wake the coder; wait until that item is `done` or parked (a `asyncio.Future` the runtime resolves in `_run` when an understand task ends), then take `result.summary`. If it parked, use the description and say so in the feed.
- The coder runs `understand` tasks exactly like reviews (read-only tools, no MCP, no checkpoint) with
  `UNDERSTAND_SYSTEM_PROMPT`: read the README, package files and entry points first; finish with what the
  app is for, who it's for, how it's built (stack, main pages/screens, data), what's missing or broken,
  under 250 words.
- **Clarify:** `ask_json(llm, LIGHTNING, ..., KickoffQuestions)` with `KICKOFF_SYSTEM` (below). On a bad
  answer, skip straight to planning. Each question goes through `ask_and_wait` with `task_id=None`.
- **Plan:** `create_plan(llm, description, context=...)` — the existing planner gains an optional `context`
  string appended to its user message, and its system prompt gains: "When an existing project is described,
  plan changes to that project, not a new app." Items are added with `add_plan_item(..., status "draft")`
  using fresh ids (`next_task_id`).
- Model errors anywhere in the kickoff post `ai.error` (existing throttle) and a `kickoff.step` "Kickoff
  stopped: …"; partial results stay (answered questions, no plan).

### Prompts

`KICKOFF_SYSTEM`: "You help a team decide what to build before any code changes. From the idea and the
project summary, ask 2 or 3 questions whose answers would change the plan most (audience, scope of the first
version, keep or change the existing design, must-have features). Each question has 2 to 4 short options and
a default (the safest choice). Don't ask what the summary already answers. JSON only:
{"questions": [{"question": "...", "options": ["..."], "default": "..."}]}". `default` must be one of the
options (validated; otherwise the first option).

### Web

- Create and import dialogs (`app/dashboard/page.tsx`): a "Plan it with me" checkbox, on by default,
  remembered per browser. After create (idea) the dashboard calls `api.kickoff(room.id)`. For imports the
  room page calls it once the imported files' saves have settled (`Promise.allSettled` of the uploads in
  `loadInitialFiles`), using a flag stashed with the import.
- The plan's empty state (`PlanList.tsx`) gets a **Plan it with me** button (owner) that calls the endpoint.
- The feed shows `kickoff.step` as coordinator lines.
- `api.kickoff(id)`; event types `kickoff.requested`, `kickoff.step`.

## Error handling

| Situation | Result |
|---|---|
| No model | 409; the dashboard (or the plan's button) shows "No AI model, so planning didn't start" |
| Kickoff already running | 409 "Planning is already running" |
| Understand task parks | Feed: "Couldn't read the project; planning from the description" |
| Coordinator questions malformed twice | Skip questions; plan from description + summary |
| Planner fails twice | The existing one-task fallback plan (draft) |
| Model error | `ai.error` + "Kickoff stopped: …" |

## Testing

- Runtime (FakeLLM): idea room → 2 questions asked one at a time (second only after the first is answered),
  answers reach the planner's prompt, drafts added; import room (files present) → understand task runs
  read-only first and its summary reaches the questions prompt; a question that times out uses its default;
  malformed questions → plan anyway; model error → notices, no crash.
- API: owner only, 409 without a model, 409 while running, survives as an event.
- Planner: `context` appears in the user message; existing tests unchanged.
- Web: `tsc`, lint, build.

## Out of scope

Resuming a kickoff after a restart; editing the questions; running the Superpowers skill text itself.
