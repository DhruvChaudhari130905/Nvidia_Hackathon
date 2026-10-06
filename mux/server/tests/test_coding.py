"""The room's coder worker: approved tasks run through CoderLoop with room tools, logs and checkpoints."""

import asyncio
import json
from itertools import count
from uuid import uuid4

import pytest

from mux.agents.llm import LLMReply, ToolCall, Usage
from mux.events.models import PlanItem
from mux.memory.task_log import LogDraft
from mux.replay.fake_llm import FakeLLM
from mux.replay.fake_sandbox import FakeSandbox
from mux.rooms.actor import RoomActor
from mux.rooms.coding import RoomCoder, next_task
from mux.sandbox.client import RunResult
from mux.sandbox.runner import BUILD_CMD, Runner, wrap

TEMPLATE = {"CONVENTIONS.md": b"Use React function components.\n", "src/App.tsx": b"export const App = 1\n"}
_ids = count(1)


@pytest.fixture
def published():
    return []


@pytest.fixture
def publish(published):
    async def _publish(event):
        published.append(event)
    return _publish


async def new_room(session_factory, publish, *statuses):
    owner = uuid4()
    actor = await RoomActor.create(owner, "Todo app", publish, template=TEMPLATE, sessionmaker=session_factory)
    items = [PlanItem(id=f"t{n}", title=f"Task {n}", status=s) for n, s in enumerate(statuses, start=1)]
    if items:
        await actor.draft_plan(items, "owner")
    return actor, owner


def calls(*tool_calls, text=""):
    """One coder turn: some tool calls, as the model sends them."""
    return LLMReply(
        text=text, model="fake-super", usage=Usage(10, 5),
        tool_calls=[ToolCall(f"c{next(_ids)}", name, args, json.dumps(args)) for name, args in tool_calls],
    )


def finish(summary="Done"):
    return calls(("finish_task", {"summary": summary}))


def log(app="A todo app", *changed):
    return LogDraft(app=app, changed=list(changed))


def sandbox(*exit_codes):
    fake = FakeSandbox({wrap("build", BUILD_CMD): [RunResult(c, "src/App.tsx:1: broken" if c else "", None, 2.0)
                                                  for c in exit_codes]})
    return fake


def types(published):
    return [e.type for e in published]


def next_id(actor):
    item = next_task(actor)
    return item.id if item else None


def status(actor, task_id="t1"):
    return next(item.status for item in actor.plan if item.id == task_id)


async def test_a_task_runs_builds_finishes_and_checkpoints(session_factory, publish, published):
    actor, _ = await new_room(session_factory, publish, "todo", "todo")
    llm = FakeLLM([
        calls(("write_file", {"path": "src/List.tsx", "content": "export const List = 1\n"}), ("run_build", {}),
              text="I will add the list."),
        finish("Added the list"),
        log("A todo app with a list", "Created src/List.tsx"),
    ])
    coder = RoomCoder(actor, llm, runner=Runner(sandbox(0), actor.get_blob, "mux-starter"))
    result = await coder.run_task(actor.plan[0])

    assert result.status == "done"
    assert [item.status for item in actor.plan] == ["done", "todo"]
    assert "src/List.tsx" in actor.files.manifest
    kinds = types(published)
    for kind in ("task.started", "agent.text", "tool.called", "file.changed", "build.result", "tool.result",
                 "task.finished", "checkpoint.created", "log.task_written"):
        assert kind in kinds
    build = next(e for e in published if e.type == "build.result")
    assert build.payload["passed"] and build.payload["snapshot_uuid"] == "fake-1"
    assert actor.record.head_checkpoint_id is not None
    head = actor.checkpoints[actor.record.head_checkpoint_id]
    assert head.sandbox_snapshot_uuid == "fake-1"
    current, _ = await actor.logs()
    assert current is not None and "A todo app with a list" in current.body
    assert actor.budget.runs_used == 1 and actor.budget.tokens_used > 0

    context = "\n".join(m["content"] for m in llm.calls[0].messages)
    assert "Use React function components." in context  # CONVENTIONS.md from the room's files
    assert "[t1] Task 1" in context and "src/App.tsx" in context  # the task and the repo map
    task_log_prompt = llm.calls[2].messages[1]["content"]
    assert "Created src/List.tsx" in task_log_prompt and "Build passed" in task_log_prompt


async def test_the_next_task_rules(session_factory, publish):
    actor, owner = await new_room(session_factory, publish, "draft", "draft")
    assert next_task(actor) is None  # the plan awaits approval
    await actor.approve_plan(str(owner))
    assert next_id(actor) == "t1"
    await actor.start_task("t2")
    assert next_id(actor) == "t2"  # a task in progress (a restart, an interrupt) goes first
    await actor.set_budget_caps(1, 10, str(owner))
    await actor.charge(tokens=1)
    assert next_task(actor) is None  # paused


async def test_the_next_task_log_rolls_the_previous_one_forward(session_factory, publish):
    actor, _ = await new_room(session_factory, publish, "todo", "todo")
    llm = FakeLLM([finish(), log("First log"), finish(), log("Second log")])
    coder = RoomCoder(actor, llm)
    await coder.run_task(actor.plan[0])
    await coder.run_task(next(i for i in actor.plan if i.id == "t2"))
    assert "First log" in "\n".join(m["content"] for m in llm.calls[2].messages)  # the room log in the context
    assert "First log" in llm.calls[3].messages[1]["content"]  # the previous log in the next task log


async def test_a_question_parks_the_task(session_factory, publish):
    actor, _ = await new_room(session_factory, publish, "todo", "todo")
    llm = FakeLLM([calls(("ask_room", {"question": "Stripe or fake?", "options": ["Stripe", "Fake"], "default": "Fake"}))])
    await RoomCoder(actor, llm).run_task(actor.plan[0])
    assert status(actor) == "skipped_question"
    [question] = actor.cards.questions.values()
    assert (question.task_id, question.default) == ("t1", "Fake")
    assert next_id(actor) == "t2"  # the coder goes on with other work


async def test_an_interrupt_stops_and_keeps_the_task_for_a_fresh_start(session_factory, publish, published):
    actor, _ = await new_room(session_factory, publish, "todo")
    actor.interrupt_requested = True
    llm = FakeLLM([calls(("list_files", {"path": "."}))])
    await RoomCoder(actor, llm).run_task(actor.plan[0])
    assert status(actor) == "doing" and not actor.interrupt_requested
    assert types(published)[-1] == "turn.interrupted"


async def test_merged_notes_and_edit_notes_arrive_at_the_turn_boundary(session_factory, publish):
    actor, owner = await new_room(session_factory, publish, "todo")
    llm = FakeLLM([calls(("list_files", {"path": "."})), finish(), log()])
    coder = RoomCoder(actor, llm)
    original = llm.chat

    async def chat(role, messages, **kwargs):
        reply = await original(role, messages, **kwargs)
        if len(llm.calls) == 1:  # during the first turn: a teammate's message and a manual edit
            await actor.add_note("t1", "make the button blue")
            await actor.lock_file("src/App.tsx", owner)
            await actor.save_file("src/App.tsx", b"export const App = 2\n", 1, owner)
        return reply

    llm.chat = chat
    await coder.run_task(actor.plan[0])
    second = [m["content"] for m in llm.calls[1].messages if m["role"] == "user"]
    assert "make the button blue" in second
    assert any("edited src/App.tsx (v1 -> v2)" in m for m in second)


async def test_a_repeated_call_blocks_the_task(session_factory, publish, published):
    actor, _ = await new_room(session_factory, publish, "todo", "todo")
    same = ("read_file", {"path": "src/App.tsx"})
    llm = FakeLLM([calls(same), calls(same), calls(same)])
    await RoomCoder(actor, llm).run_task(actor.plan[0])
    assert status(actor) == "blocked"
    assert actor.plan[0].merged_notes == ["Blocked: blocked: repeated tool call"]
    assert "Set the task back to todo" in published[-1].payload["text"]
    assert next_id(actor) == "t2"


async def test_the_coder_splits_its_task(session_factory, publish):
    actor, _ = await new_room(session_factory, publish, "todo", "todo")
    llm = FakeLLM([calls(("update_plan", {"task_id": "t1", "split": ["Table", "Filters"]})), finish(), log()])
    await RoomCoder(actor, llm).run_task(actor.plan[0])
    assert [(i.id, i.title, i.status) for i in actor.plan] == [
        ("t1", "Table", "done"), ("t3", "Filters", "todo"), ("t2", "Task 2", "todo"),
    ]


async def test_a_file_a_person_is_editing_is_read_only(session_factory, publish):
    actor, owner = await new_room(session_factory, publish, "todo")
    await actor.connect(owner, "Ana")
    await actor.lock_file("src/App.tsx", owner)
    tool = ("edit_file", {"path": "src/App.tsx", "base_version": 1, "edits": [{"find": "1", "replace": "2"}]})
    llm = FakeLLM([calls(tool), finish(), log()])
    await RoomCoder(actor, llm).run_task(actor.plan[0])
    result = json.loads(next(m for m in llm.calls[1].messages if m["role"] == "tool")["content"])
    assert result["ok"] is False and "being edited by Ana" in result["error"]
    data, version = await actor.read_file("src/App.tsx")
    assert (data, version) == (b"export const App = 1\n", 1)


async def test_closed_votes_are_pinned_in_the_task_log(session_factory, publish):
    actor, owner = await new_room(session_factory, publish, "todo")
    card = await actor.open_conflict([], "Sidebar or top bar?", ["Sidebar", "Top bar"], "ui", "use a top bar")
    await actor.override(card.id, "Top bar", owner)
    llm = FakeLLM([finish(), log()])
    await RoomCoder(actor, llm).run_task(actor.plan[0])
    current, _ = await actor.logs()
    assert current is not None
    assert current.pins == [{"kind": "override", "conflict_id": str(card.id),
                             "text": "Sidebar or top bar?: the owner chose 'Top bar'"}]
    assert "the owner chose 'Top bar'" in current.body


async def test_the_day_log_compacts_the_sitting(session_factory, publish, published):
    actor, owner = await new_room(session_factory, publish, "todo", "todo")
    llm = FakeLLM([finish(), log("Log 1"), finish(), log("Log 2"), log("The day")])
    coder = RoomCoder(actor, llm)
    await coder.run_task(actor.plan[0])
    await coder.run_task(next(i for i in actor.plan if i.id == "t2"))
    await coder.write_day_log("owner")
    prompt = llm.calls[4].messages[1]["content"]
    assert "Log 1" in prompt and "Log 2" in prompt
    current, logs = await actor.logs()
    assert current is not None and (current.kind, "The day" in current.body) == ("day", True)
    assert types(published)[-1] == "log.day_written"
    await coder.write_day_log("idle")  # no task since the day log: nothing to write
    assert len((await actor.logs())[1]) == len(logs)


async def test_the_worker_runs_approved_tasks_and_waits(session_factory, publish):
    actor, owner = await new_room(session_factory, publish, "draft")
    llm = FakeLLM([finish(), log()])
    coder = RoomCoder(actor, llm)
    coder.start()
    try:
        await asyncio.sleep(0.05)
        assert llm.calls == []  # nothing approved yet
        await actor.approve_plan(str(owner))
        for _ in range(100):
            if status(actor) == "done":
                break
            await asyncio.sleep(0.05)
        assert status(actor) == "done"
        assert actor.on_sitting_end == coder.write_day_log
    finally:
        await coder.stop()
    assert actor.on_sitting_end is None
