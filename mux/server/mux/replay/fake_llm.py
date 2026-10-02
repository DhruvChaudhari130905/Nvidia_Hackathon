"""Fake LLM that replays recorded coordinator and coder outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from mux.agents.llm import DeltaCallback, LLMReply, ModelRole, Usage

Scripted = str | BaseModel | LLMReply | Exception


@dataclass
class Call:
    role: ModelRole
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None
    schema: type[BaseModel] | None
    reasoning: bool | None
    max_tokens: int | None


class FakeLLM:
    def __init__(self, script: list[Scripted] | None = None, *, chunk_size: int = 8) -> None:
        self._script: list[Scripted] = list(script or [])
        self._chunk_size = chunk_size
        self.calls: list[Call] = []

    def push(self, *items: Scripted) -> None:
        self._script.extend(items)

    @property
    def remaining(self) -> int:
        return len(self._script)

    async def chat(
            self,
            role: ModelRole,
            messages: list[dict[str, Any]],
            *,
            tools: list[dict[str, Any]] | None = None,
            schema: type[BaseModel] | None = None,
            reasoning: bool | None = None,
            max_tokens: int | None = None,
            on_delta: DeltaCallback | None = None,
    ) -> LLMReply:
        # copy, because callers like the coder loop keep appending to the same list
        self.calls.append(Call(role, list(messages), tools, schema, reasoning, max_tokens))
        if not self._script:
            raise AssertionError(f"FakeLLM script is empty on call {len(self.calls)}")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        reply = _to_reply(item, role)
        if on_delta is not None:
            for i in range(0, len(reply.text), self._chunk_size):
                await on_delta(reply.text[i : i + self._chunk_size])
        return reply


def _to_reply(item: str | BaseModel | LLMReply, role: ModelRole) -> LLMReply:
    if isinstance(item, LLMReply):
        return item
    text = item.model_dump_json() if isinstance(item, BaseModel) else item
    # rough 4 characters per token, so budget code sees non-zero usage
    usage = Usage(prompt_tokens=0, completion_tokens=max(1, len(text) // 4))
    return LLMReply(text=text, model=f"fake-{role.value}", usage=usage, finish_reason="stop")
