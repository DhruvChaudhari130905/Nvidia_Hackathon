"""The room runtime: coordinator labels, plans, votes and questions, and the coder working through tasks.

Real registry, actors and runtimes; only the model is scripted (FakeLLM).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest

import mux.rooms.registry as room_registry
from mux.agents.coder.tools.files import ActorFileTools
from mux.agents.coordinator.schema import AddPlanItem, CoordinatorAction, OpenConflict, PlanDraft, PlanItemDraft
from mux.agents.llm import LLMReply, ToolCall, Usage
from mux.events.log import InMemoryEventLog
from mux.events.models import AgentNoticeEvent, BaseEvent, EventType
from mux.events.wire import to_envelope
from mux.replay.fake_llm import FakeLLM
from mux.rooms.actor import RoomActor
from mux.rooms.registry import RoomRegistry
from mux.rooms.runtime import RETRY, SKIP, RoomRuntime

PLAN = PlanDraft(tasks=[PlanItemDraft(title="Booking page")])


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the actor's FileStore lives under cwd
    logs: dict[str, InMemoryEventLog] = {}
    monkeypatch.setattr(room_registry, "get_event_log", lambda rid: logs.setdefault(rid, InMemoryEventLog(rid)))
    llm = FakeLLM()
    runtimes: list[RoomRuntime] = []

    def factory(actor: RoomActor) -> RoomRuntime:
        rt = RoomRuntime(actor, llm, vote_timeout=30, question_timeout=30, max_turns=3)
        runtimes.append(rt)
        return rt

    return RoomRegistry(runtime_factory=factory), llm, logs, runtimes


async def until(check: Callable[[], Any], timeout: float = 3.0) -> None:
    """Wait for background work (event callbacks, the coder) to reach a state."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        result = check()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timed out waiting for the runtime")
        await asyncio.sleep(0.01)


def notices(log: InMemoryEventLog, kind: str) -> list[dict[str, Any]]:
    return [e.data for e in log._events if isinstance(e, AgentNoticeEvent) and e.kind == kind]


def of_type(log: InMemoryEventLog, t: EventType) -> list[BaseEvent]:
    return [e for e in log._events if e.type == t]


async def new_room(registry: RoomRegistry, llm: FakeLLM, logs, *, domain_role: str | None = "design") -> RoomActor:
    llm.push(PLAN)
    actor = await registry.create_room("room_test1", "alice", name="Yoga", description="Yoga booking", domain_role=domain_role)
    await until(lambda: actor.get_plan())
    return actor


def tool_reply(*calls: tuple[str, dict[str, Any]]) -> LLMReply:
    return LLMReply(
        text="", model="fake-super", usage=Usage(10, 5), finish_reason="tool_calls",
        tool_calls=[ToolCall(f"c{i}", name, args, json.dumps(args)) for i, (name, args) in enumerate(calls)],
    )


@pytest.mark.asyncio
async def test_room_creation_drafts_the_plan(setup):
    registry, llm, logs, _ = setup
    actor = await new_room(registry, llm, logs)
    plan = await actor.get_plan()
    assert [(p["id"], p["title"], p["status"]) for p in plan] == [("t1", "Booking page", "draft")]
    assert (await actor.get_budget_status())["tokens_used"] > 0  # the planner's tokens count against the room
    await registry.shutdown_all()


@pytest.mark.asyncio
async def test_messages_are_labeled_and_applied(setup):
    registry, llm, logs, _ = setup
    actor = await new_room(registry, llm, logs)
    log = logs[actor.room_id]

    llm.push(CoordinatorAction(label="chat", rationale="a question", reply="It uses SQLite."))
    await actor.add_message("chat", "what db do we use?", message_id="m1", user_id="alice", enqueue=False)
    await until(lambda: notices(log, "coordinator.reply"))
    assert notices(log, "message.labeled")[0] == {"message_id": "m1", "label": "chat", "rationale": "a question", "domain": None}
    reply = to_envelope(of_type(log, EventType.AGENT_NOTICE)[-1])
    assert reply is not None and reply["type"] == "coordinator.reply" and reply["payload"]["text"] == "It uses SQLite."

    llm.push(CoordinatorAction(label="queue", rationale="new work", add_plan_item=AddPlanItem(title="Pricing page")))
    await actor.add_message("chat", "add a pricing page", message_id="m2", user_id="alice", enqueue=False)
    await until(lambda: len(of_type(log, EventType.PLAN_ITEM_ADDED)) == 1)
    # The plan isn't approved yet, so the new work joins the draft and the coder doesn't start
    assert [(p["title"], p["status"]) for p in await actor.get_plan()] == [("Booking page", "draft"), ("Pricing page", "draft")]
    assert not of_type(log, EventType.TASK_STARTED)

    llm.push(CoordinatorAction(label="merge", rationale="fits", domain="ui"))
    await actor.add_message("chat", "bigger headings", message_id="m3", user_id="alice", enqueue=False)
    await until(lambda: len(notices(log, "message.labeled")) == 3)
    merges, _, interrupt = await actor.drain_inbox()
    assert merges == ["bigger headings"] and not interrupt

    # Team notes never reach the coordinator
    calls = len(llm.calls)
    await actor.add_message("chat", "@bob login?", message_id="m4", user_id="alice", to="team", enqueue=False)
    await asyncio.sleep(0.05)
    assert len(llm.calls) == calls
    await registry.shutdown_all()


@pytest.mark.asyncio
async def test_conflict_vote_is_role_weighted(setup):
    registry, llm, logs, _ = setup
    actor = await new_room(registry, llm, logs, domain_role="design")
    await actor.add_member("bob", "editor", granted_by="alice", domain_role="eng")
    log = logs[actor.room_id]

    llm.push(CoordinatorAction(
        label="conflict", rationale="contradicts", domain="ui",
        open_conflict=OpenConflict(with_message_ids=["m1"], summary="Dark or light theme", options=["Dark", "Light"]),
    ))
    await actor.add_message("chat", "make it dark", message_id="m1", user_id="bob", enqueue=False)
    await until(lambda: of_type(log, EventType.CONFLICT_DETECTED))
    opened = to_envelope(of_type(log, EventType.CONFLICT_DETECTED)[0])
    assert opened is not None and opened["payload"]["options"] == ["Dark", "Light"]
    cid = opened["payload"]["id"]

    # 1-1 on heads, but Design owns UI, so alice's vote counts 2
    await actor.command_vote(option_id="Light", issued_by="alice", vote_value=True, plan_item_id=cid)
    await actor.command_vote(option_id="Dark", issued_by="bob", vote_value=True, plan_item_id=cid)
    await until(lambda: of_type(log, EventType.CONFLICT_RESOLVED))
    resolved = of_type(log, EventType.CONFLICT_RESOLVED)[0]
    assert resolved.resolution == "Light"  # type: ignore[attr-defined]
    assert resolved.resolution_details["totals"] == {"Dark": 1, "Light": 2}  # type: ignore[attr-defined]
    await until(lambda: len(actor.inbox) == 1)  # the decision reaches the coder at its next turn
    merges, _, _ = await actor.drain_inbox()
    assert merges == ['The room decided "Light" on: Dark or light theme']
    await registry.shutdown_all()


@pytest.mark.asyncio
async def test_coder_builds_approved_tasks(setup):
    registry, llm, logs, _ = setup
    actor = await new_room(registry, llm, logs)
    log = logs[actor.room_id]

    llm.push(
        tool_reply(("write_file", {"path": "src/Booking.tsx", "content": "export const Booking = () => null;\n"})),
        tool_reply(("finish_task", {"summary": "Added the booking page"})),
    )
    await actor.approve_plan_items(["t1"], "alice")
    await until(lambda: of_type(log, EventType.CHECKPOINT_CREATED))

    assert await actor.get_file("src/Booking.tsx") == "export const Booking = () => null;\n"
    assert (await actor.get_plan())[0]["status"] == "done"
    types = [env["type"] for env in map(to_envelope, log._events) if env]
    for expected in ("task.started", "tool.called", "tool.result", "file.changed", "agent.text", "task.finished", "checkpoint.created"):
        assert expected in types, types
    changed = next(e for e in map(to_envelope, log._events) if e and e["type"] == "file.changed")
    assert changed["actor"] == "coder" and changed["payload"]["version"] == 1
    await registry.shutdown_all()


@pytest.mark.asyncio
async def test_stopped_task_is_parked_behind_a_question(setup):
    registry, llm, logs, _ = setup
    actor = await new_room(registry, llm, logs)
    log = logs[actor.room_id]

    # max_turns=3 and the model never calls a tool: the turn limit stops the task
    llm.push("thinking", "still thinking", "hmm")
    await actor.approve_plan_items(["t1"], "alice")
    await until(lambda: of_type(log, EventType.QUESTION_ASKED))
    asked = to_envelope(of_type(log, EventType.QUESTION_ASKED)[0])
    assert asked is not None and asked["payload"]["options"] == [RETRY, SKIP] and asked["payload"]["default_option"] == SKIP
    assert (await actor.get_plan())[0]["status"] == "skipped_question"

    # Retry puts it back in the queue and the coder runs it again
    llm.push(tool_reply(("finish_task", {"summary": "done this time"})))
    await actor.command_answer_question(asked["payload"]["id"], RETRY, "alice")
    await until(lambda: of_type(log, EventType.CHECKPOINT_CREATED))
    assert (await actor.get_plan())[0]["status"] == "done"
    await registry.shutdown_all()


@pytest.mark.asyncio
async def test_coder_never_overwrites_a_locked_or_newer_file(setup):
    registry, llm, logs, _ = setup
    actor = await new_room(registry, llm, logs)
    tools = ActorFileTools(actor)

    assert (await tools.write_file("a.ts", "one"))["version"] == 1
    # A person saves v2 after the coder read v1: the coder's edit is stale, not an overwrite
    assert await actor.save_checked("a.ts", "two", 1, "alice") == ("ok", 2)
    stale = await tools.edit_file("a.ts", 1, [{"find": "one", "replace": "uno"}])
    assert stale["ok"] is False and stale["current_version"] == 2

    await actor.lock_file("a.ts", "alice")
    locked = await tools.edit_file("a.ts", 2, [{"find": "two", "replace": "dos"}])
    assert locked["ok"] is False and "locked" in locked["error"]
    assert await actor.get_file("a.ts") == "two"
    await registry.shutdown_all()
