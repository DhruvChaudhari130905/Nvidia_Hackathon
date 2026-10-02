"""Hand-rolled coder loop with turn and task boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from mux.agents.coder.compaction import compact
from mux.agents.coder.escalation import EscalationState
from mux.agents.llm import LLM, DeltaCallback, LLMReply, ModelRole, Usage

NUDGE = "Continue with tool calls, or call finish_task when the task is done."


class ToolExecutor(Protocol):
    async def execute(self, name: str, arguments: dict[str, Any]) -> Any: ...


class BoundaryProvider(Protocol):
    async def turn_boundary(self) -> TurnBoundary: ...
    async def task_boundary(self, task_id: str, summary: str) -> None: ...


@dataclass(frozen=True)
class TurnBoundary:
    merges: tuple[str, ...] = ()
    edit_notes: tuple[str, ...] = ()
    interrupt: bool = False


@dataclass(frozen=True)
class CoderTask:
    id: str
    title: str


@dataclass(frozen=True)
class CoderResult:
    task_id: str
    status: Literal["done", "stopped"]
    turns: int
    model: ModelRole
    summary: str = ""
    usage: Usage = field(default_factory=Usage)  # every turn of this task, for the room budget


class CoderLoop:
    def __init__(
        self,
        llm: LLM,
        tools: ToolExecutor,
        actor: BoundaryProvider,
        tool_schemas: list[dict[str, Any]],
        *,
        max_turns: int = 25,
        reasoning: bool | None = None,  # None until the spike confirms Token Factory's switch
        on_text_delta: DeltaCallback | None = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.actor = actor
        self.tool_schemas = tool_schemas
        self.max_turns = max_turns
        self.reasoning = reasoning
        self.on_text_delta = on_text_delta

    async def run_task(self, task: CoderTask, messages: list[dict[str, Any]]) -> CoderResult:
        state = EscalationState(max_turns=self.max_turns)
        context = list(messages)
        usage = Usage()

        while state.next_turn():
            reply = await self.llm.chat(
                state.model, context, tools=self.tool_schemas,
                reasoning=self.reasoning, on_delta=self.on_text_delta,
            )
            usage = Usage(usage.prompt_tokens + reply.usage.prompt_tokens,
                          usage.completion_tokens + reply.usage.completion_tokens)
            context.append({"role": "assistant", "content": reply.text or "", **_tool_calls_message(reply)})

            finished: str | None = None
            stopped: str | None = None
            for call in reply.tool_calls:
                if call.arguments is None:
                    context.append(_tool_message(call.id, "Invalid JSON arguments. Retry this tool call with valid JSON."))
                    continue
                if state.record_tool_call(call.name, call.arguments):
                    context.append(_tool_message(call.id, {"ok": False, "error": "loop_detected"}))
                    stopped = "blocked: repeated tool call"
                    break

                result = await self.tools.execute(call.name, call.arguments)
                context.append(_tool_message(call.id, result))

                if call.name == "run_build":
                    passed = bool(_result_value(result, "passed", False))
                    was_ultra = state.model == ModelRole.ULTRA  # Super's errors must not count against Ultra
                    state.record_build(passed)
                    if not passed and was_ultra and state.record_ultra_error(str(_result_value(result, "errors", ""))):
                        stopped = "blocked: repeated Ultra build error"
                        break
                elif call.name == "finish_task" and _result_value(result, "ok", False):
                    finished = str(_result_value(result, "summary", "")) or "task finished"

            if stopped:
                return await self._finish(task, state, usage, "stopped", stopped)
            if finished:
                # messages not yet handed over stay in the actor's inbox for the next task
                return await self._finish(task, state, usage, "done", finished)
            if not reply.tool_calls:
                context.append({"role": "user", "content": NUDGE})

            context = compact(context)
            boundary = await self.actor.turn_boundary()
            if boundary.interrupt:
                return await self._finish(task, state, usage, "stopped", "interrupted and needs replanning")
            for item in (*boundary.merges, *boundary.edit_notes):
                context.append({"role": "user", "content": item})

        return await self._finish(task, state, usage, "stopped", "turn limit reached")

    async def _finish(
            self, task: CoderTask, state: EscalationState, usage: Usage,
            status: Literal["done", "stopped"], summary: str,
    ) -> CoderResult:
        await self.actor.task_boundary(task.id, summary)
        return CoderResult(task.id, status, state.turns, state.model, summary, usage)


def _tool_calls_message(reply: LLMReply) -> dict[str, Any]:
    if not reply.tool_calls:
        return {}
    return {
        "tool_calls": [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.raw_arguments}}
            for call in reply.tool_calls
        ]
    }


def _tool_message(call_id: str, result: Any) -> dict[str, Any]:
    content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _result_value(value: Any, key: str, default: Any) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
