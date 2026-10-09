# Room Kickoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "Plan it with me": a room created from an idea or an imported project gets a plan drafted from its own code and the team's answers to 2–3 multiple-choice questions.

**Architecture:** `POST /rooms/{id}/kickoff` records a `kickoff_requested` event. The room runtime then runs one background kickoff: a read-only "understand" coder task (when the room has files) produces a summary; the coordinator asks questions one at a time through the existing question cards (`ask_and_wait`); the existing planner, now taking extra context, drafts plan items. The web app calls the endpoint from the create/import dialogs and from the empty plan.

**Tech Stack:** Python / FastAPI / pydantic; Next.js / React / TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-10-room-kickoff-design.md`

## Global Constraints

- Backend tests: `.venv/bin/python -m pytest` from `mux/server`; full suite `make test-server` from the repo root.
- Questions: 1–3 per kickoff (the prompt asks for 2–3), each 2–4 options, `default` one of the options (else the first option), asked one at a time.
- Plan: drafted items have status `draft` and fresh ids from `next_task_id`; appended when the plan already has items.
- Understand and review tasks are read-only (no write tools, no MCP, no checkpoint).
- Feed notices: `kickoff.step` `{text}` with exactly these texts: `"Reading your project…"`, `"Couldn't read the project; planning from the description"`, `"Question {n} of {total}"`, `"Plan drafted from your answers — approve it to start"`, `"Kickoff stopped: {reason}"`.
- API: owner only; 409 `"This room has no AI model, so planning can't start"` without a model; 409 `"Planning is already running"` while one runs.

## Review Focus

- **Someone keeps chatting during the kickoff**: messages are still labelled and applied as usual; the kickoff's questions and plan aren't disturbed. Test in Task 3 (a message posted mid-kickoff gets its label).
- **The understand task parks** (turn limit or model error): the kickoff continues from the description and says so. Test in Task 3.
- **Nobody answers a question**: it takes its default when the card expires and the kickoff carries on. Test in Task 3.
- **The room stops (owner deletes it) mid-kickoff**: the kickoff task is cancelled with the runtime; no errors. Test in Task 3 (shutdown while a question waits).
- **The coordinator returns options without a valid default**: the first option is used. Test in Task 1.

---

## File Structure

| File | Responsibility |
|---|---|
| `mux/server/mux/agents/coordinator/schema.py` | `KickoffQuestion`, `KickoffQuestions` |
| `mux/server/mux/agents/coordinator/kickoff.py` | `KICKOFF_SYSTEM`, `ask_kickoff_questions` |
| `mux/server/mux/agents/coordinator/planner.py` | `create_plan(..., context=)` |
| `mux/server/mux/agents/coder/prompts.py` | `UNDERSTAND_SYSTEM_PROMPT` |
| `mux/server/mux/events/models.py`, `events/wire.py`, `rooms/actor.py` | `kickoff_requested` event, `request_kickoff` |
| `mux/server/mux/rooms/runtime.py` | read-only kinds, task waiters, `_kickoff`, `kickoff_running`, `model_available` |
| `mux/server/mux/api/rooms.py` | `POST /rooms/{id}/kickoff` |
| `mux/web/src/...` | dialogs, import flag, plan button, feed line |

---

### Task 1: Questions schema, kickoff prompt, planner context

**Files:**
- Modify: `mux/server/mux/agents/coordinator/schema.py` (after `Review`), `mux/server/mux/agents/coordinator/planner.py` (`PLAN_SYSTEM`, `create_plan`)
- Create: `mux/server/mux/agents/coordinator/kickoff.py`
- Test: `mux/server/tests/test_coordinator.py` (append)

**Interfaces:**
- Produces: `KickoffQuestion(question: str, options: list[str], default: str)`, `KickoffQuestions(questions: list[KickoffQuestion])`; `async ask_kickoff_questions(llm: LLM, description: str, summary: str) -> tuple[KickoffQuestions | None, Usage]`; `create_plan(llm, description, *, context: str = "", reasoning=None) -> PlanResult`.

- [ ] **Step 1: Write the failing tests**

Append to `mux/server/tests/test_coordinator.py`:

```python


# --- kickoff ----------------------------------------------------------------------

def test_kickoff_question_default_must_be_an_option():
    from mux.agents.coordinator.schema import KickoffQuestion, KickoffQuestions
    q = KickoffQuestion(question="Who is it for?", options=["Students", "Teachers"], default="Parents")
    assert q.default == "Students"
    assert KickoffQuestions(questions=[q]).questions[0].options == ["Students", "Teachers"]
    import pytest as _pytest
    with _pytest.raises(ValueError):
        KickoffQuestion(question="x", options=["only one"], default="only one")


@pytest.mark.asyncio
async def test_kickoff_questions_see_the_idea_and_summary():
    from mux.agents.coordinator.kickoff import ask_kickoff_questions
    from mux.agents.coordinator.schema import KickoffQuestion, KickoffQuestions
    llm = FakeLLM()
    llm.push(KickoffQuestions(questions=[KickoffQuestion(question="Scope?", options=["Small", "Big"], default="Small")]))
    questions, usage = await ask_kickoff_questions(llm, "A yoga booking app", "React app with a schedule page")
    assert questions is not None and questions.questions[0].question == "Scope?"
    prompt = "\n".join(m["content"] for m in llm.calls[0].messages)
    assert "A yoga booking app" in prompt and "React app with a schedule page" in prompt


@pytest.mark.asyncio
async def test_kickoff_questions_give_up_on_bad_answers():
    from mux.agents.coordinator.kickoff import ask_kickoff_questions
    llm = FakeLLM()
    llm.push("not json", "still not json")
    questions, _ = await ask_kickoff_questions(llm, "idea", "summary")
    assert questions is None


@pytest.mark.asyncio
async def test_planner_uses_the_kickoff_context():
    llm = FakeLLM()
    llm.push(PlanDraft(tasks=[{"title": "Add a cart page"}]))  # type: ignore[list-item]
    result = await create_plan(llm, "Imported project: shop", context="The team's answers:\n- Scope? Small")
    assert [i.title for i in result.items] == ["Add a cart page"]
    prompt = "\n".join(m["content"] for m in llm.calls[0].messages)
    assert "The team's answers" in prompt and "plan changes to that project" in prompt
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_coordinator.py -q -k "kickoff or planner_uses"`
Expected: FAIL (`ImportError: cannot import name 'KickoffQuestion'`)

- [ ] **Step 3: Implement**

In `mux/server/mux/agents/coordinator/schema.py`, after the `Review` class:

```python


class KickoffQuestion(BaseModel):
    """One multiple-choice question the kickoff asks the team (a question card)."""
    question: str = Field(min_length=1, max_length=200)
    options: list[str] = Field(min_length=2, max_length=4)
    default: str = ""

    @model_validator(mode="after")
    def _default_is_an_option(self) -> KickoffQuestion:
        self.options = [o.strip()[:80] for o in self.options if o.strip()]
        if len(self.options) < 2:
            raise ValueError("a question needs at least 2 options")
        if self.default not in self.options:
            self.default = self.options[0]
        return self


class KickoffQuestions(BaseModel):
    questions: list[KickoffQuestion] = Field(min_length=1, max_length=3)
```

Create `mux/server/mux/agents/coordinator/kickoff.py`:

```python
"""Kickoff questions: what to ask the team before planning (the brainstorming step of "Plan it with me")."""

from __future__ import annotations

from typing import Optional

from mux.agents.coordinator.agent import ask_json
from mux.agents.coordinator.schema import KickoffQuestions
from mux.agents.llm import LLM, ModelRole, Usage

KICKOFF_SYSTEM = """You help a team decide what to build before any code changes.
From the idea and the project summary, ask 2 or 3 questions whose answers would change the plan most:
audience, scope of the first version, keep or change the existing design, must-have features.
Each question has 2 to 4 short options and a default (the safest choice). Don't ask what the summary already answers.
Answer with JSON only:
{"questions": [{"question": "...", "options": ["..."], "default": "..."}]}"""


async def ask_kickoff_questions(llm: LLM, description: str, summary: str) -> tuple[Optional[KickoffQuestions], Usage]:
    """The questions to ask, or None when the model's answers weren't usable twice (plan without them)."""
    messages = [
        {"role": "system", "content": KICKOFF_SYSTEM},
        {"role": "user", "content": f"Idea:\n{description or '(none given)'}\n\nProject summary:\n{summary or '(no files yet)'}"},
    ]
    result = await ask_json(llm, ModelRole.LIGHTNING, messages, KickoffQuestions, max_tokens=600)
    return result.value, result.usage
```

In `mux/server/mux/agents/coordinator/planner.py`, in `PLAN_SYSTEM` replace the line `- No setup tasks: the stack, tools, and hosting are already chosen.` with:

```
- No setup tasks: the stack, tools, and hosting are already chosen.
- When an existing project is described, plan changes to that project, not a new app.
```

and replace `create_plan`'s signature and messages:

```python
async def create_plan(llm: LLM, description: str, *, context: str = "", reasoning: bool | None = None) -> PlanResult:
    # always Super: plan quality matters and it runs once per room
    user = f"App description:\n{description}" + (f"\n\n{context}" if context else "")
    messages = [
        {"role": "system", "content": PLAN_SYSTEM},
        {"role": "user", "content": user},
    ]
```

(The rest of `create_plan` is unchanged.)

- [ ] **Step 4: Run the tests**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_coordinator.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add mux/server/mux/agents/coordinator mux/server/tests/test_coordinator.py
git commit -m "Add kickoff questions and let the planner use project context"
```

---

### Task 2: Kickoff event and endpoint

**Files:**
- Modify: `mux/server/mux/events/models.py`, `mux/server/mux/events/wire.py`, `mux/server/mux/rooms/actor.py`, `mux/server/mux/rooms/runtime.py` (`model_available`, `kickoff_running`), `mux/server/mux/api/rooms.py`, `mux/web/src/types/index.ts` (union)
- Test: `mux/server/tests/test_api.py` (append)

**Interfaces:**
- Produces: `KickoffRequestedEvent(requested_by: str)`; `async actor.request_kickoff(user_id)`; `RoomRuntime.model_available() -> bool`; `RoomRuntime.kickoff_running: bool` (property, `self._kickoff_task` not done); `POST /rooms/{id}/kickoff`; wire `kickoff.requested`.

- [ ] **Step 1: Write the failing tests**

Append to `mux/server/tests/test_api.py`:

```python


# --- kickoff -------------------------------------------------------------------

def test_kickoff_needs_the_owner_and_a_model(client):
    rid = create_room(client)
    client.post(f"/rooms/{rid}/members", json={"user_id": "bob", "role": "editor"}, headers=auth("alice"))
    assert client.post(f"/rooms/{rid}/kickoff", headers=auth("bob")).status_code == 403
    r = client.post(f"/rooms/{rid}/kickoff", headers=auth("alice"))
    assert r.status_code == 409 and "no AI model" in r.json()["detail"]


def test_kickoff_is_recorded_and_not_run_twice(client, monkeypatch):
    import asyncio
    rid = create_room(client)
    runtime = room_registry.get_registry().runtime(rid)
    assert runtime is not None
    monkeypatch.setattr(runtime, "_model_available", lambda: True)

    async def no_kickoff() -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(runtime, "_kickoff", no_kickoff)
    assert client.post(f"/rooms/{rid}/kickoff", headers=auth("alice")).json() == {"accepted": True}
    for _ in range(50):
        if runtime.kickoff_running:
            break
        time.sleep(0.02)
    r = client.post(f"/rooms/{rid}/kickoff", headers=auth("alice"))
    assert r.status_code == 409 and r.json()["detail"] == "Planning is already running"
    with client.websocket_connect(f"/rooms/{rid}/ws?since=0&token={token('alice')}") as ws:
        assert '"kickoff.requested"' in ws.receive_text()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_api.py -q -k kickoff`
Expected: FAIL (404 on `/kickoff`)

- [ ] **Step 3: Event, actor, wire**

`events/models.py` — in `EventType` after `ROOM_SKILLS_SET` if present, else after `ROOM_AI_SETTINGS_CLEARED`:

```python
    KICKOFF_REQUESTED = "kickoff_requested"
```

after the last room-settings event class (`RoomSkillsSetEvent` if present, else `RoomAiSettingsClearedEvent`):

```python


class KickoffRequestedEvent(BaseEvent):
    """The owner asked MUX to plan the room with the team ("Plan it with me")."""
    type: EventType = EventType.KICKOFF_REQUESTED
    requested_by: str = Field(..., description="User who asked")
```

and add it to the `Event` union and `__all__` next to that class.

`events/wire.py` — import `KickoffRequestedEvent` is not needed; before `# Invites (room_invite_*) aren't sent` add:

```python
    if t == EventType.KICKOFF_REQUESTED:
        return "kickoff.requested", {}
```

`rooms/actor.py` — import `KickoffRequestedEvent` with the other room events, and after `clear_ai_settings` (or `set_skills` if present):

```python

    async def request_kickoff(self, user_id: str) -> None:
        """Ask the room's runtime to plan the room with the team (rooms/runtime.py _kickoff)."""
        async with self._lock:
            await self._emit(KickoffRequestedEvent(**self._event_fields(user_id), requested_by=user_id))
```

`web/src/types/index.ts` — after `| 'ai.error'` add:

```ts
  | 'kickoff.requested'
  | 'kickoff.step'
```

- [ ] **Step 4: Runtime state and endpoint**

`rooms/runtime.py` — in `__init__` after `self._last_model_error = float("-inf")`:

```python
        self._kickoff_task: Optional[asyncio.Task] = None
        self._task_waiters: dict[str, asyncio.Future[tuple[str, str]]] = {}  # plan item id -> (status, summary)
```

and add after `_model_available`:

```python
    def model_available(self) -> bool:
        return self._model_available()

    @property
    def kickoff_running(self) -> bool:
        return self._kickoff_task is not None and not self._kickoff_task.done()

    async def _kickoff(self) -> None:
        """Plan the room with the team. Filled in by the next task."""
        return None
```

In `_handle`, after the `ROOM_AI_SETTINGS_SAVED` branch (before `if not self._model_available(): return`) leave as is, and add after the model check:

```python
        if t == EventType.KICKOFF_REQUESTED:
            if not self.kickoff_running:
                self._kickoff_task = asyncio.create_task(self._kickoff())
            return
```

In `stop`, change `for task in [*self._tasks, *self._timers]:` to:

```python
        kickoff = [self._kickoff_task] if self._kickoff_task is not None else []
        for task in [*self._tasks, *self._timers, *kickoff]:
```

and the `gather` line to `await asyncio.gather(*self._tasks, *self._timers, *kickoff, return_exceptions=True)`.

`api/rooms.py` — add after the `close_room` endpoint:

```python
@router.post("/{room_id}/kickoff")
async def kickoff(
    room_id: str,
    current_user: User = Depends(require_owner),
    actor: RoomActor = Depends(get_room_actor),
) -> dict[str, Any]:
    """Owner only: "Plan it with me". The room's runtime reads the project, asks the team and drafts a plan."""
    runtime = get_registry().runtime(room_id)
    if runtime is None or not runtime.model_available():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This room has no AI model, so planning can't start")
    if runtime.kickoff_running:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Planning is already running")
    await actor.request_kickoff(current_user.id)
    return {"accepted": True}
```

- [ ] **Step 5: Run the tests**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_api.py -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add mux/server/mux/events mux/server/mux/rooms mux/server/mux/api/rooms.py mux/server/tests/test_api.py mux/web/src/types/index.ts
git commit -m "Add the kickoff request: event, runtime state and endpoint"
```

---

### Task 3: The kickoff in the runtime

**Files:**
- Modify: `mux/server/mux/agents/coder/prompts.py` (after `REVIEW_SYSTEM_PROMPT`), `mux/server/mux/rooms/runtime.py` (imports; `_run`; `_context`; `_kickoff`; helpers)
- Test: `mux/server/tests/test_runtime.py` (append)

**Interfaces:**
- Consumes: T1 `ask_kickoff_questions`, `create_plan(..., context=)`; T2 `_kickoff_task`, `_task_waiters`, `KICKOFF_REQUESTED`; existing `ask_and_wait`, `_plan_items`, `next_task_id`, `_spend`, `_model_error`.
- Produces: `UNDERSTAND_SYSTEM_PROMPT`; plan items with `kind: "understand"`; `kickoff.step` notices.

- [ ] **Step 1: Write the failing tests**

Append to `mux/server/tests/test_runtime.py`:

```python


# --- kickoff ----------------------------------------------------------------------

@pytest.fixture
def quick(tmp_path, monkeypatch):
    """Like `setup`, with question cards that expire after 0.3 s."""
    monkeypatch.chdir(tmp_path)
    logs: dict[str, InMemoryEventLog] = {}
    monkeypatch.setattr(room_registry, "get_event_log", lambda rid: logs.setdefault(rid, InMemoryEventLog(rid)))
    llm = FakeLLM()
    return RoomRegistry(runtime_factory=lambda a: RoomRuntime(a, llm, vote_timeout=30, question_timeout=0.3, max_turns=3)), llm, logs


def kickoff_steps(log) -> list[str]:
    return [d["text"] for d in notices(log, "kickoff.step")]


def two_questions():
    from mux.agents.coordinator.schema import KickoffQuestion, KickoffQuestions
    return KickoffQuestions(questions=[
        KickoffQuestion(question="Who is it for?", options=["Students", "Studios"], default="Studios"),
        KickoffQuestion(question="First version?", options=["Booking only", "Booking and payments"], default="Booking only"),
    ])


@pytest.mark.asyncio
async def test_kickoff_from_an_idea_asks_one_question_at_a_time_then_drafts_a_plan(setup):
    from mux.agents.coordinator.schema import PlanDraft
    registry, llm, logs, _ = setup
    actor = await new_room(registry, llm, logs, plan=None)
    log = logs[actor.room_id]
    llm.push(two_questions())
    await actor.request_kickoff("alice")

    await until(lambda: of_type(log, EventType.QUESTION_ASKED))
    first = to_envelope(of_type(log, EventType.QUESTION_ASKED)[0])
    assert first is not None and first["payload"]["text"] == "Who is it for?"
    await asyncio.sleep(0.1)
    assert len(of_type(log, EventType.QUESTION_ASKED)) == 1  # the second waits for the first answer
    # A message during the kickoff is still labelled as usual (queued before the planner's answer, so the
    # fake model hands each call its own reply)
    llm.push(CoordinatorAction(label="chat", rationale="a question", reply="Yes."))
    await actor.add_message("chat", "is this working?", message_id="m1", user_id="alice", enqueue=False)
    await until(lambda: notices(log, "message.labeled"))
    await actor.command_answer_question(first["payload"]["id"], "Students", "alice")
    await until(lambda: len(of_type(log, EventType.QUESTION_ASKED)) == 2)
    second = to_envelope(of_type(log, EventType.QUESTION_ASKED)[1])
    assert second is not None
    llm.push(PlanDraft(tasks=[{"title": "Class schedule page"}, {"title": "Booking form"}]))  # type: ignore[list-item]
    await actor.command_answer_question(second["payload"]["id"], "Booking and payments", "bob")
    await until(lambda: any("Plan drafted" in s for s in kickoff_steps(log)))

    plan = await actor.get_plan()
    assert [(p["title"], p["status"]) for p in plan] == [("Class schedule page", "draft"), ("Booking form", "draft")]
    planner_prompt = "\n".join(m["content"] for m in llm.calls[-1].messages)
    assert "Who is it for? Students" in planner_prompt and "First version? Booking and payments" in planner_prompt
    assert kickoff_steps(log) == ["Question 1 of 2", "Question 2 of 2", "Plan drafted from your answers — approve it to start"]
    assert notices(log, "message.labeled")  # the chat message was handled
    await registry.shutdown_all()


@pytest.mark.asyncio
async def test_kickoff_reads_an_imported_project_first(setup):
    from mux.agents.coordinator.schema import PlanDraft
    registry, llm, logs, _ = setup
    actor = await new_room(registry, llm, logs, plan=None)
    log = logs[actor.room_id]
    await actor.create_file("src/App.jsx", "export default function Shop() { return null; }\n", "alice")
    llm.push(
        tool_reply(("read_file", {"path": "src/App.jsx"})),
        tool_reply(("finish_task", {"summary": "A shop app with one empty page; no cart yet."})),
        two_questions(),
        PlanDraft(tasks=[{"title": "Add a cart"}]),  # type: ignore[list-item]
    )
    await actor.request_kickoff("alice")
    await until(lambda: len(of_type(log, EventType.QUESTION_ASKED)) == 1)

    understand = next(p for p in await actor.get_plan() if p.get("kind") == "understand")
    assert understand["status"] == "done"
    coder_tools = {t["function"]["name"] for t in next(c for c in llm.calls if c.tools).tools or []}
    assert "write_file" not in coder_tools
    questions_prompt = "\n".join(m["content"] for m in llm.calls[2].messages)
    assert "A shop app with one empty page" in questions_prompt
    assert kickoff_steps(log)[0] == "Reading your project…"
    assert not of_type(log, EventType.CHECKPOINT_CREATED)
    await registry.shutdown_all()


@pytest.mark.asyncio
async def test_unanswered_questions_take_their_default(quick):
    from mux.agents.coordinator.schema import PlanDraft
    registry, llm, logs = quick
    actor = await new_room(registry, llm, logs, plan=None)
    log = logs[actor.room_id]
    llm.push(two_questions(), PlanDraft(tasks=[{"title": "Studio dashboard"}]))  # type: ignore[list-item]
    await actor.request_kickoff("alice")
    await until(lambda: any("Plan drafted" in s for s in kickoff_steps(log)), timeout=5)
    planner_prompt = "\n".join(m["content"] for m in llm.calls[-1].messages)
    assert "Who is it for? Studios" in planner_prompt and "First version? Booking only" in planner_prompt
    await registry.shutdown_all()


@pytest.mark.asyncio
async def test_kickoff_without_usable_questions_still_plans(setup):
    from mux.agents.coordinator.schema import PlanDraft
    registry, llm, logs, _ = setup
    actor = await new_room(registry, llm, logs, plan=None)
    log = logs[actor.room_id]
    llm.push("not json", "still not json", PlanDraft(tasks=[{"title": "Home page"}]))  # type: ignore[list-item]
    await actor.request_kickoff("alice")
    await until(lambda: any("Plan drafted" in s for s in kickoff_steps(log)))
    assert not of_type(log, EventType.QUESTION_ASKED)
    assert [p["title"] for p in await actor.get_plan()] == ["Home page"]
    await registry.shutdown_all()


@pytest.mark.asyncio
async def test_a_failed_understand_task_falls_back_to_the_description(setup):
    from mux.agents.coordinator.schema import PlanDraft
    registry, llm, logs, _ = setup
    actor = await new_room(registry, llm, logs, plan=None)
    log = logs[actor.room_id]
    await actor.create_file("a.js", "x", "alice")
    # max_turns=3 and the coder never finishes: the understand task parks
    llm.push("thinking", "still thinking", "hmm", "not json", "nope", PlanDraft(tasks=[{"title": "Home page"}]))  # type: ignore[list-item]
    await actor.request_kickoff("alice")
    await until(lambda: any("Plan drafted" in s for s in kickoff_steps(log)))
    assert "Couldn't read the project; planning from the description" in kickoff_steps(log)
    await registry.shutdown_all()


@pytest.mark.asyncio
async def test_model_errors_stop_the_kickoff_cleanly(switchable):
    from mux.agents.llm import ModelError
    registry, llm, logs = switchable
    actor = await new_room(registry, llm, logs, plan=None)
    log = logs[actor.room_id]
    llm.on = True
    llm.error = ModelError("429 rate limited")
    await actor.request_kickoff("alice")
    await until(lambda: any(s.startswith("Kickoff stopped") for s in kickoff_steps(log)))
    assert notices(log, "ai.error") == [{"error": "429 rate limited"}]
    await registry.shutdown_all()


@pytest.mark.asyncio
async def test_stopping_the_room_mid_kickoff_is_clean(setup):
    registry, llm, logs, _ = setup
    actor = await new_room(registry, llm, logs, plan=None)
    log = logs[actor.room_id]
    llm.push(two_questions())
    await actor.request_kickoff("alice")
    await until(lambda: of_type(log, EventType.QUESTION_ASKED))
    await registry.shutdown_all()  # cancels the waiting kickoff without errors
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_runtime.py -q -k "kickoff or default or understand or mid_kickoff"`
Expected: FAIL (timeouts: the Task 2 `_kickoff` stub does nothing)

- [ ] **Step 3: The understand prompt**

In `mux/server/mux/agents/coder/prompts.py`, after `REVIEW_SYSTEM_PROMPT`:

```python


UNDERSTAND_SYSTEM_PROMPT = """You are the MUX coder agent, getting to know a project before the team plans. You don't change anything.

Your job: read enough of the project to explain it, then call finish_task once with the summary.

Rules:
- Only read. Writing, editing, deleting and builds are not available.
- Read the README and package files first, then the entry points and the main pages or screens.
- Don't read a file twice unless an earlier read says it was dropped.
- finish_task's summary, under 250 words: what the app is for and who it's for; how it's built (stack,
  main pages or screens, where data comes from); what's missing, unfinished or broken."""
```

- [ ] **Step 4: Read-only kinds and task waiters in `_run` / `_context`**

In `mux/server/mux/rooms/runtime.py`:

- Change the import `from mux.agents.coder.prompts import REVIEW_SYSTEM_PROMPT, coder_system_prompt` to `from mux.agents.coder.prompts import REVIEW_SYSTEM_PROMPT, UNDERSTAND_SYSTEM_PROMPT, coder_system_prompt`, and add `from mux.agents.coordinator.kickoff import ask_kickoff_questions` and `from mux.agents.coordinator.planner import create_plan, next_task_id` (replacing the existing `from mux.agents.coordinator.planner import next_task_id`).

- In `_run`, replace `review = item.get("kind") == "review"` with:

```python
        kind = item.get("kind")
        review = kind in ("review", "understand")  # read-only tasks: no write tools, no MCP, no checkpoint
        outcome: tuple[str, str] = ("stopped", "")
```

  change `await self._context(item, executor.can_build, review=review)` to `await self._context(item, executor.can_build, kind=kind)`; directly after `await self._spend(result.usage, CODER)` add `outcome = (result.status, result.summary)`; in the `except Exception as e:` block add `outcome = ("stopped", str(e))` as its first line; and in the `finally:` block (which sets `self._current_task = None`) add:

```python
            waiter = self._task_waiters.pop(task_id, None)
            if waiter is not None and not waiter.done():
                waiter.set_result(outcome)
```

- Change `_context`'s signature to `async def _context(self, item: dict[str, Any], can_build: bool, *, kind: Optional[str] = None) -> list[dict[str, Any]]:` and its `system_prompt=` line to:

```python
            system_prompt={"review": REVIEW_SYSTEM_PROMPT, "understand": UNDERSTAND_SYSTEM_PROMPT}.get(kind or "")
            or coder_system_prompt(can_build),
```

- [ ] **Step 5: The kickoff**

Replace the Task 2 stub `_kickoff` with:

```python
    async def _kickoff(self) -> None:
        """"Plan it with me": understand the project, ask the team, draft a plan (spec 2026-10-10)."""
        try:
            meta = self.actor.manifest.get_room_metadata()
            description = (meta.get("description") or meta.get("name") or "").strip()
            summary = description
            if await self.actor.list_files():
                await self._step("Reading your project…")
                status, text = await self._understand()
                if status == "done" and text:
                    summary = text
                else:
                    await self._step("Couldn't read the project; planning from the description")
            questions, usage = await ask_kickoff_questions(self.llm, description, summary)
            await self._spend(usage, COORDINATOR)
            answers: list[tuple[str, str]] = []
            if questions is not None:
                total = len(questions.questions)
                for n, q in enumerate(questions.questions, 1):
                    await self._step(f"Question {n} of {total}")
                    answers.append((q.question, await self.ask_and_wait(q.question, q.options, q.default, None)))
            context = f"Project summary:\n{summary or '(none)'}"
            if answers:
                context += "\n\nThe team's answers:\n" + "\n".join(f"- {q} {a}" for q, a in answers)
            result = await create_plan(self.llm, description or "(no description)", context=context)
            await self._spend(result.usage, COORDINATOR)
            for item in result.items:
                new: dict[str, Any] = {"id": next_task_id(await self._plan_items()), "title": item.title, "status": "draft"}
                if item.notes:
                    new["notes"] = item.notes
                if item.owner_role:
                    new["owner_role"] = item.owner_role
                await self.actor.add_plan_item(new, COORDINATOR)
            await self._step("Plan drafted from your answers — approve it to start")
        except asyncio.CancelledError:
            raise
        except ModelError as e:
            await self._model_error(e)
            await self._step(f"Kickoff stopped: {e}")
        except Exception:
            logger.exception(f"Room {self.actor.room_id}: kickoff failed")
            await self._step("Kickoff stopped: something went wrong")

    async def _understand(self) -> tuple[str, str]:
        """Run a read-only "understand" task and wait for it: (status, summary)."""
        item_id = next_task_id(await self._plan_items())
        waiter: asyncio.Future[tuple[str, str]] = asyncio.get_running_loop().create_future()
        self._task_waiters[item_id] = waiter
        await self.actor.add_plan_item(
            {"id": item_id, "title": "Understand the project", "status": "todo", "kind": "understand"}, COORDINATOR,
        )
        self._wake.set()
        return await waiter

    async def _step(self, text: str) -> None:
        await self.actor.post_notice("kickoff.step", {"text": text})
```

If `PlanItem` (from `mux.agents.coordinator.prompts`) has no `notes` / `owner_role` attributes, use `getattr(item, "notes", None)` / `getattr(item, "owner_role", None)`.

- [ ] **Step 6: Run the tests**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_runtime.py -q && .venv/bin/python -m pytest -q && .venv/bin/pyright mux tests scripts`
Expected: all pass; pyright `0 errors`.

- [ ] **Step 7: Commit**

```bash
git add mux/server/mux/agents/coder/prompts.py mux/server/mux/rooms/runtime.py mux/server/tests/test_runtime.py
git commit -m "Plan rooms with the team: understand, ask, then draft a plan"
```

---

### Task 4: Web: "Plan it with me"

**Files:**
- Modify: `mux/web/src/lib/api.ts`, `mux/web/src/lib/projectImport.ts` (`ImportResult`), `mux/web/src/app/dashboard/page.tsx`, `mux/web/src/app/room/[roomId]/page.tsx`, `mux/web/src/components/side/PlanList.tsx`, `mux/web/src/components/side/SidePanel.tsx`, `mux/web/src/lib/reducer.ts`, `mux/web/src/lib/preferences.ts`

**Interfaces:**
- Consumes: `POST /rooms/{id}/kickoff`.
- Produces: `api.kickoff(id)`; `ImportResult.kickoff?: boolean`; `getPlanWithMe()` / `setPlanWithMe(on)`; `PlanList` prop `onKickoff?: () => void`; `SidePanel` prop `onKickoff`.

- [ ] **Step 1: API, preference, feed**

`lib/api.ts`, after `approvePlan`:

```ts
  // Owner only: "Plan it with me" (read the project, ask the team, draft a plan). 409 without an AI model
  kickoff: (roomId: string) =>
    fetchWithAuth<{ accepted: true }>(`/rooms/${roomId}/kickoff`, { method: 'POST' }),
```

and in `demoFetch` before the `/github/connect` line: `if (roomMatch && roomMatch[2] === '/kickoff') return { accepted: true } as T;`

`lib/preferences.ts` — append:

```ts
// "Plan it with me" in the create and import dialogs: on unless this browser turned it off
const PLAN_WITH_ME_KEY = 'mux.planWithMe';

export function getPlanWithMe(): boolean {
  try {
    return localStorage.getItem(PLAN_WITH_ME_KEY) !== 'off';
  } catch {
    return true;
  }
}

export function setPlanWithMe(on: boolean): void {
  try {
    localStorage.setItem(PLAN_WITH_ME_KEY, on ? 'on' : 'off');
  } catch {
    // private window: the default (on) applies next time
  }
}
```

`lib/reducer.ts`, before `case 'ai.changed':`:

```ts
    case 'kickoff.step': {
      const { text } = (event as unknown as { payload: { text: string } }).payload;
      newState.messages = [...newState.messages, {
        id: `kickoff-${event.seq}`,
        room_id: newState.room.id,
        user_id: 'coordinator',
        text,
        created_at: event.ts,
        user: { id: 'coordinator', email: '', name: 'Coordinator', initials: 'CO', color: 'hsl(190, 70%, 60%)' },
      } as Message];
      break;
    }
    case 'kickoff.requested':
      break;
```

- [ ] **Step 2: Dashboard dialogs**

`lib/projectImport.ts` — in `ImportResult` add `kickoff?: boolean; // "Plan it with me": the room page starts it once the files are saved`.

`app/dashboard/page.tsx`:

- Import `getPlanWithMe, setPlanWithMe` from `@/lib/preferences` (extend the existing import).
- Add state after `newRoomPassword`: `const [planWithMe, setPlanWithMeState] = useState(true);` and in `loadData` after `setNewRoomRole(getDefaultRole());` add `setPlanWithMeState(getPlanWithMe());`.
- In `handleCreateRoom`, after `const room = await api.createRoom(...)`:

```tsx
      if (planWithMe) {
        api.kickoff(room.id).catch(error => alert(error instanceof Error ? `Planning didn't start: ${error.message}` : "Planning didn't start"));
      }
```

- In `importProject`, change `stashImport(room.id, result);` to `stashImport(room.id, { ...result, kickoff: getPlanWithMe() });`.
- Pass to `CreateRoomDialog` the props `planWithMe={planWithMe}` and `onPlanWithMeChange={on => { setPlanWithMeState(on); setPlanWithMe(on); }}`; add `planWithMe: boolean; onPlanWithMeChange: (on: boolean) => void;` to `CreateRoomDialogProps`, destructure them, and before the buttons row (`<div className="flex justify-end gap-space-sm border-t ...">`) add:

```tsx
          <label className="flex items-start gap-2 text-body-sm text-on-surface-variant">
            <input type="checkbox" className="mt-1" checked={planWithMe} onChange={e => onPlanWithMeChange(e.target.checked)} />
            <span><span className="font-bold text-on-surface">Plan it with me</span> — the agents ask a few questions, then draft a plan for you to approve.</span>
          </label>
```

- Next to the **Import project** button, add a small checkbox using the same preference:

```tsx
        <label className="flex items-center gap-1.5 text-label-md text-on-surface-variant" title="After importing, read the project, ask a few questions and draft a plan">
          <input type="checkbox" checked={planWithMe} onChange={e => { setPlanWithMeState(e.target.checked); setPlanWithMe(e.target.checked); }} />
          Plan it with me
        </label>
```

- [ ] **Step 3: Room page: kickoff after an import's files are saved, and the plan button**

`app/room/[roomId]/page.tsx`, in `loadInitialFiles` replace the `imported.files.forEach(...)` block with:

```tsx
      const saves = imported.files.map(f =>
        api.saveFile(roomId, f.path, f.content, null)
          .then(({ version }) => writeLocal([{ path: f.path, content: f.content, version }]))
          .catch(error => console.error(`Could not save ${f.path} to the room:`, error)),
      );
      // "Plan it with me": start once the agents can read every file
      if (imported.kickoff) {
        void Promise.allSettled(saves).then(() => api.kickoff(roomId))
          .catch(error => console.error("Planning didn't start:", error));
      }
```

Add a handler near `handlePlanApprove`:

```tsx
  const handleKickoff = useCallback(async () => {
    try {
      await api.kickoff(roomId);
    } catch (error) {
      alert(error instanceof Error ? `Planning didn't start: ${error.message}` : "Planning didn't start");
    }
  }, [roomId]);
```

and pass `onKickoff={handleKickoff}` to `<SidePanel ...>`.

`components/side/SidePanel.tsx`: add `onKickoff: () => void;` to its props interface, destructure it, and pass `onKickoff={onKickoff}` to `<PlanList ...>` (only owners get the button: PlanList checks `canApprove`).

`components/side/PlanList.tsx`: add `onKickoff?: () => void;` to `PlanListProps`, destructure it, and replace the empty-state paragraph with:

```tsx
      {plan.length === 0 && (
        <div className="space-y-2">
          <p className="text-[12px] text-[var(--faint)]">Tell the agent what to build in the chat. Each request shows up here as a task.</p>
          {canApprove && onKickoff && (
            <button className="btn w-full" onClick={onKickoff} type="button">Plan it with me</button>
          )}
        </div>
      )}
```

- [ ] **Step 4: Type-check, lint, build**

Run: `cd mux/web && npx tsc --noEmit && npm run lint -- --max-warnings=0 && NEXT_DIST_DIR=.next-build npm run build`
Expected: no errors; `✓ Compiled successfully`.

- [ ] **Step 5: Commit**

```bash
git add mux/web/src
git commit -m "Add Plan it with me to the create and import dialogs and the empty plan"
```

---

### Task 5: Docs

**Files:**
- Modify: `docs/03-getting-started.md`

- [ ] **Step 1: Add a section after "Working on one room together"**

```markdown
## 🧭 Plan it with me

When you create a room or import a project with **Plan it with me** ticked (it is by default), MUX plans with you before building:

1. **Understand:** for an imported project, the coder reads it (README, package files, entry points, main pages) without changing anything and posts a summary.
2. **Ask:** the coordinator asks 2–3 multiple-choice questions, one at a time, as cards in **Decisions & plan**. Anyone in the room can answer; an unanswered card takes its default.
3. **Plan:** it drafts tasks from your idea, the summary and the answers. The owner reviews them and presses **Approve plan** to start building.

The feed shows each step. An empty plan has a **Plan it with me** button for rooms created without it. It needs an AI model (the server's or the room's own); without one, nothing starts.
```

- [ ] **Step 2: Verify and commit**

Run: `make test-server`
Expected: all pass.

```bash
git add docs/03-getting-started.md
git commit -m "Document Plan it with me"
```
