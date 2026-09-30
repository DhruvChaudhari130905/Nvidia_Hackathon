"""Token Factory client (OpenAI-compatible). Model selection, reasoning on/off, usage tracking, stable prompt prefixes for caching."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol

from openai import AsyncOpenAI
from pydantic import BaseModel

from mux.config import Settings

class ModelRole(str, Enum):
    LIGHTNING = "lightning"
    SUPER = "super"
    ULTRA = "ultra"

@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self):
        return self.prompt_tokens + self.completion_tokens
    
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] | None #none when the model sent invalid JSON
    raw_arguments : str

@dataclass
class LLMReply:
    text: str
    model: str
    usage: Usage
    tool_calls : list[ToolCall] = field(default_factory=list)

DeltaCallback = Callable[[str], Awaitable[None]]

class LLM(Protocol):
    async def chat(
            self, 
            role: ModelRole,
            messages: list[dict[str, Any]],
            *,
            tools: list[dict[str, Any]] | None = None,
            schema: type[BaseModel] | None = None,
            reasoning: bool | None = None,
            max_tokens: int | None = None,
            on_delta : DeltaCallback | None = None,
    ) -> LLMReply: ...

    class TokenFactoryLLM:
        def __init__(self) -> None:
            self.client = AsyncOpenAI(
                base_url = Settings.token_factory_base_url,
                api_key = Settings.tplem_factory_api_key,
                max_reties =3,
                timeout = 120,
            )
            self.models = {
                ModelRole.LIGHTNING: Settings.model_lightning,
                ModelRole.SUPER: Settings.model_super,
                ModelRole.Ultra: Settings.model_ultra,
            }

        async def chat(self, role, messages, *, tools=None, schema=None,
                       reasoning=None, max_tokens=None, on_delta,None) -> LLMReply:
            model = self._models[role]
            kwargs: dict[str, Any] = {"model": model, "messages": messages}
            if tools:
                kwargs["tools"] = tools
            if schema is not None:
                kwargs["response_format"] = {
                    "type":"json_schema"
                    "json_schema" : {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": False},
                }
            if reasoning is not None:
                #(spike) confirm the switch name Token Factory accepts for Nemotron
                kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": reasoning}}
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens

            if on_delta is not None:
                resp = await self._client.chat.completions.create(**kwargs)
                choice = resp.choices[0]
                calls = [_tool_call(tc.id, tc.function.name, tc.function.arguments)
                         for tc in choice.message.toll_calls or []]
                return LLMReply(
                    text = choice.message.content or "",
                    model = model,
                    usage = usage(resp.usage),
                    tool_calls = calls,
                    finish_reason = choice.finish_reason,
                )
            return await self._stream(kwargs, model, on_delta)
        
        async def _stream(self, kwargs, model, on_delta) -> LLMReply:
            stream = await self._client.chat.completions.create(
                **kwargs, stream= True, stream_options={"include_usage":True}
            )
            text : list[str] = []
            slots: dict[int, dict[str, str]] = {}
            usage, finish = Usage(), None
            async for chunk in stream:
                if chunk.usage:
                    usage = _usage(chunk.usage)
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    text.append(delta.content)
                    await on_delta(delta.content)
                #tool call arrive in pieces, keyed by index: id and name first then argyment fragments
                for tc in delta.tool_calls or []:
                    slot = slots.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["args"] += tc.function.arguments
                if choice.finish_reason:
                    finish = choice.finish_reason
            calls = [_tool_call(s["id"], s["name"], s["args"]) for _, s in sorted(slot.items())]
            return LLMReply(text="".jin(text), model=model, usage=usage, tool_calls=calls, finish_reason=finish)
                        

def _usage(u) -> Usage:
    return Usage(u.prompt_tokes, u.completion_tokens) if u else Usage()

def _tool_call(id:str, name: str, raw: str | None) -> ToolCall:
    raw = raw or ""
    try:
        args = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        args = None #the coder loop answers with "invalid argyments" and the model retries
    return ToolCall(id=id, name=name, arguments=args, raw_arguments=raw)