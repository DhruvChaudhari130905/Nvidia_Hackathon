"""Tests for the coder loop."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from mux.agents.coder.loop import (
    CoderLoop,
    CoderTask,
    TurnBoundary,
)
from mux.agents.llm import (
    LLMReply,
    ModelRole,
    ToolCall,
    Usage,
)
from mux.replay.fake_llm import FakeLLM


class FakeTools:
    def __init__(
        self,
        handler: Callable[
            [str, dict[str, Any]],
            Awaitable[Any],
        ]
        | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.handler = handler

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        self.calls.append((name, arguments))

        if self.handler is not None:
            return await self.handler(name, arguments)

        if name == "finish_task":
            return {
                "ok": True,
                "summary": arguments.get(
                    "summary",
                    "finished",
                ),
            }

        return {"ok": True}


class FakeActor:
    def __init__(
        self,
        boundaries: list[TurnBoundary] | None = None,
    ) -> None:
        self.boundaries = list(boundaries or [])
        self.turn_boundary_calls = 0
        self.task_boundaries: list[tuple[str, str]] = []

    async def turn_boundary(self) -> TurnBoundary:
        self.turn_boundary_calls += 1

        if self.boundaries:
            return self.boundaries.pop(0)

        return TurnBoundary()

    async def task_boundary(
        self,
        task_id: str,
        summary: str,
    ) -> None:
        self.task_boundaries.append(
            (task_id, summary)
        )


def tool_call(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    call_id: str = "call-1",
) -> ToolCall:
    import json

    args = arguments or {}

    return ToolCall(
        id=call_id,
        name=name,
        arguments=arguments,
        raw_arguments=json.dumps(args),
    )


def reply(
    *calls: ToolCall,
    text: str = "",
) -> LLMReply:
    return LLMReply(
        text=text,
        model="fake",
        usage=Usage(),
        tool_calls=list(calls),
    )


@pytest.mark.asyncio
async def test_finish_task_reaches_task_boundary():
    llm = FakeLLM(
        [
            reply(
                tool_call(
                    "finish_task",
                    {"summary": "Implemented feature"},
                )
            )
        ]
    )
    tools = FakeTools()
    actor = FakeActor()

    loop = CoderLoop(
        llm,
        tools,
        actor,
        [],
    )

    result = await loop.run_task(
        CoderTask("t1", "Implement feature"),
        [{"role": "user", "content": "Build it"}],
    )

    assert result.status == "done"
    assert result.turns == 1
    assert result.summary == "Implemented feature"

    # a finished task goes straight to the task boundary; unmerged messages stay in the inbox
    assert actor.turn_boundary_calls == 0
    assert actor.task_boundaries == [
        ("t1", "Implemented feature")
    ]


@pytest.mark.asyncio
async def test_interrupt_stops_task_at_turn_boundary():
    llm = FakeLLM(
        [
            reply(text="Working...")
        ]
    )
    tools = FakeTools()
    actor = FakeActor(
        [
            TurnBoundary(
                interrupt=True,
            )
        ]
    )

    loop = CoderLoop(
        llm,
        tools,
        actor,
        [],
    )

    result = await loop.run_task(
        CoderTask("t1", "Implement feature"),
        [],
    )

    assert result.status == "stopped"
    assert result.summary == (
        "interrupted and needs replanning"
    )
    assert result.turns == 1
    assert actor.task_boundaries == [
        ("t1", "interrupted and needs replanning")
    ]


@pytest.mark.asyncio
async def test_merges_and_edit_notes_are_added_after_boundary():
    llm = FakeLLM(
        [
            reply(text="First turn"),
            reply(
                tool_call(
                    "finish_task",
                    {"summary": "done"},
                )
            ),
        ]
    )
    tools = FakeTools()
    actor = FakeActor(
        [
            TurnBoundary(
                merges=("Use the new API",),
                edit_notes=("Alice edited App.tsx",),
            ),
            TurnBoundary(),
        ]
    )

    loop = CoderLoop(
        llm,
        tools,
        actor,
        [],
    )

    result = await loop.run_task(
        CoderTask("t1", "Implement feature"),
        [],
    )

    assert result.status == "done"
    assert result.turns == 2


@pytest.mark.asyncio
async def test_two_failed_builds_escalate_to_ultra():
    llm = FakeLLM(
        [
            reply(
                tool_call(
                    "run_build",
                    {},
                    call_id="build-1",
                )
            ),
            reply(
                tool_call(
                    "run_build",
                    {},
                    call_id="build-2",
                )
            ),
            reply(
                tool_call(
                    "finish_task",
                    {"summary": "Fixed build"},
                )
            ),
        ]
    )

    async def build_handler(
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        if name == "run_build":
            return {
                "passed": False,
                "errors": "TypeError in App.tsx",
            }

        return {
            "ok": True,
            "summary": "Fixed build",
        }

    tools = FakeTools(build_handler)
    actor = FakeActor()

    loop = CoderLoop(
        llm,
        tools,
        actor,
        [],
    )

    result = await loop.run_task(
        CoderTask("t1", "Fix build"),
        [],
    )

    assert result.status == "done"
    assert [call.role for call in llm.calls] == [
        ModelRole.SUPER,
        ModelRole.SUPER,
        ModelRole.ULTRA,
    ]


@pytest.mark.asyncio
async def test_repeated_tool_call_stops_loop():
    llm = FakeLLM(
        [
            reply(
                tool_call(
                    "read_file",
                    {"path": "App.tsx"},
                    call_id="1",
                )
            ),
            reply(
                tool_call(
                    "read_file",
                    {"path": "App.tsx"},
                    call_id="2",
                )
            ),
            reply(
                tool_call(
                    "read_file",
                    {"path": "App.tsx"},
                    call_id="3",
                )
            ),
        ]
    )

    tools = FakeTools()
    actor = FakeActor()

    loop = CoderLoop(
        llm,
        tools,
        actor,
        [],
    )

    result = await loop.run_task(
        CoderTask("t1", "Inspect files"),
        [],
    )

    assert result.status == "stopped"
    assert result.summary == (
        "blocked: repeated tool call"
    )
    assert result.turns == 3

    assert len(tools.calls) == 2
    assert actor.task_boundaries == [
        ("t1", "blocked: repeated tool call")
    ]


@pytest.mark.asyncio
async def test_max_turns_stops_task():
    llm = FakeLLM(
        [
            reply(text="still working")
            for _ in range(3)
        ]
    )
    tools = FakeTools()
    actor = FakeActor()

    loop = CoderLoop(
        llm,
        tools,
        actor,
        [],
        max_turns=3,
    )

    result = await loop.run_task(
        CoderTask("t1", "Long task"),
        [],
    )

    assert result.status == "stopped"
    assert result.turns == 3
    assert result.summary == "turn limit reached"

    assert actor.task_boundaries == [
        ("t1", "turn limit reached")
    ]


def usage_reply(*calls: ToolCall, text: str = "") -> LLMReply:
    return LLMReply(text=text, model="fake", usage=Usage(10, 5), tool_calls=list(calls))


@pytest.mark.asyncio
async def test_build_edit_build_is_not_a_loop():
    """Ultra must be able to build a third time after fixing the code."""
    builds = 0

    async def handler(name: str, arguments: dict[str, Any]) -> Any:
        nonlocal builds
        if name == "run_build":
            builds += 1
            return {"passed": builds >= 3, "errors": ["App.tsx:3: boom"]}
        return {"ok": True, "summary": "Fixed"}

    llm = FakeLLM([
        reply(tool_call("run_build", {}, call_id="b1")),
        reply(tool_call("edit_file", {"path": "App.tsx"}, call_id="e1")),
        reply(tool_call("run_build", {}, call_id="b2")),
        reply(tool_call("edit_file", {"path": "App.tsx", "n": 2}, call_id="e2")),
        reply(tool_call("run_build", {}, call_id="b3")),
        reply(tool_call("finish_task", {"summary": "Fixed"})),
    ])
    result = await CoderLoop(llm, FakeTools(handler), FakeActor(), []).run_task(CoderTask("t1", "Fix"), [])

    assert result.status == "done" and result.model == ModelRole.ULTRA and builds == 3


@pytest.mark.asyncio
async def test_super_build_error_does_not_count_against_ultra():
    async def handler(name: str, arguments: dict[str, Any]) -> Any:
        if name == "run_build":
            return {"passed": False, "errors": ["App.tsx:3: boom"]}
        return {"ok": True}

    llm = FakeLLM([
        reply(tool_call("run_build", {}, call_id="b1")),
        reply(tool_call("edit_file", {"n": 1}, call_id="e1")),
        reply(tool_call("run_build", {}, call_id="b2")),  # second Super failure: escalate
        reply(tool_call("edit_file", {"n": 2}, call_id="e2")),
        reply(tool_call("run_build", {}, call_id="b3")),  # first Ultra failure
        reply(tool_call("edit_file", {"n": 3}, call_id="e3")),
        reply(tool_call("run_build", {}, call_id="b4")),  # same error on Ultra again: stop
    ])
    result = await CoderLoop(llm, FakeTools(handler), FakeActor(), []).run_task(CoderTask("t1", "Fix"), [])

    assert result.summary == "blocked: repeated Ultra build error" and result.turns == 7


@pytest.mark.asyncio
async def test_usage_is_summed_over_turns():
    llm = FakeLLM([usage_reply(text="thinking"), usage_reply(tool_call("finish_task", {"summary": "ok"}))])
    result = await CoderLoop(llm, FakeTools(), FakeActor(), []).run_task(CoderTask("t1", "x"), [])

    assert (result.usage.prompt_tokens, result.usage.completion_tokens) == (20, 10)


@pytest.mark.asyncio
async def test_failed_finish_task_does_not_end_the_task():
    async def handler(name: str, arguments: dict[str, Any]) -> Any:
        if arguments.get("summary"):
            return {"ok": True, "summary": arguments["summary"]}
        return {"ok": False, "error": "summary is required"}

    llm = FakeLLM([
        reply(tool_call("finish_task", {"summary": ""}, call_id="f1")),
        reply(tool_call("finish_task", {"summary": "Done now"}, call_id="f2")),
    ])
    result = await CoderLoop(llm, FakeTools(handler), FakeActor(), []).run_task(CoderTask("t1", "x"), [])

    assert result.status == "done" and result.summary == "Done now" and result.turns == 2


@pytest.mark.asyncio
async def test_text_only_reply_gets_a_nudge():
    llm = FakeLLM([reply(text="I think I am done"), reply(tool_call("finish_task", {"summary": "ok"}))])
    await CoderLoop(llm, FakeTools(), FakeActor(), []).run_task(CoderTask("t1", "x"), [])

    assert "finish_task" in llm.calls[1].messages[-1]["content"]


@pytest.mark.asyncio
async def test_all_results_of_the_latest_turn_reach_the_model():
    async def handler(name: str, arguments: dict[str, Any]) -> Any:
        if name == "finish_task":
            return {"ok": True, "summary": "ok"}
        return {"ok": True, "content": arguments["path"] * 200}

    llm = FakeLLM([
        reply(tool_call("read_file", {"path": "a"}, call_id="r1"), tool_call("read_file", {"path": "b"}, call_id="r2")),
        reply(tool_call("finish_task", {"summary": "ok"})),
    ])
    await CoderLoop(llm, FakeTools(handler), FakeActor(), []).run_task(CoderTask("t1", "x"), [])

    tool_messages = [m for m in llm.calls[1].messages if m["role"] == "tool"]
    assert all("a" * 200 in m["content"] or "b" * 200 in m["content"] for m in tool_messages)

