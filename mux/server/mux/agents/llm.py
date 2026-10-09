"""OpenAI-compatible model client (Token Factory by default). Model selection, reasoning on/off, usage tracking."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol

import httpx2
from openai import AsyncOpenAI
from pydantic import BaseModel

from mux.config import settings

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
    finish_reason: str | None = None

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

class ModelError(Exception):
    """A model call failed (bad key, unknown model, rate limit, provider down). The text is safe to show."""


class NoModel(ModelError):
    """The room has no model to use."""


class OpenAILLM:
    """Any OpenAI-compatible chat completions API. `thinking` sends Nemotron's switch (Token Factory only)."""

    def __init__(self, base_url: str, api_key: str, models: dict[ModelRole, str], *, thinking: bool = False,
                 client: Any = None, max_retries: int = 3, timeout: float = 120.0,
                 transport: httpx2.AsyncBaseTransport | None = None) -> None:
        # Redirects aren't followed: a room's provider could otherwise send requests (and show their answers)
        # to addresses the URL check refused, like the cloud metadata service
        http = httpx2.AsyncClient(follow_redirects=False, timeout=timeout, transport=transport)
        self._client = client or AsyncOpenAI(base_url=base_url, api_key=api_key, max_retries=max_retries,
                                             timeout=timeout, http_client=http)
        self._models = models
        self._thinking = thinking

    async def chat(self, role, messages, *, tools=None, schema=None,
                   reasoning=None, max_tokens=None, on_delta=None) -> LLMReply:
        model = self._models[role]
        kwargs: dict[str, Any] = {"model": model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        if schema is not None:
            kwargs["response_format"] = {
                "type":"json_schema",
                "json_schema" : {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": False},
            }
        if reasoning is not None and self._thinking:
            #(spike) confirm the switch name Token Factory accepts for Nemotron
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": reasoning}}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        if on_delta is None:
            resp = await self._client.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            calls = [_tool_call(tc.id, tc.function.name, tc.function.arguments)
                     for tc in choice.message.tool_calls or []]
            return LLMReply(
                text = choice.message.content or "",
                model = model,
                usage = _usage(resp.usage),
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
        calls = [_tool_call(s["id"], s["name"], s["args"]) for _, s in sorted(slots.items())]
        return LLMReply(text="".join(text), model=model, usage=usage, tool_calls=calls, finish_reason=finish)


def TokenFactoryLLM() -> OpenAILLM:
    """The server's own model client, from the TOKEN_FACTORY_* and MODEL_* settings."""
    return OpenAILLM(
        settings.token_factory_base_url, settings.token_factory_api_key,
        {ModelRole.LIGHTNING: settings.model_lightning, ModelRole.SUPER: settings.model_super,
         ModelRole.ULTRA: settings.model_ultra},
        thinking=True,
    )


def _usage(u) -> Usage:
    return Usage(u.prompt_tokens, u.completion_tokens) if u else Usage()

def _tool_call(id:str, name: str, raw: str | None) -> ToolCall:
    raw = raw or ""
    try:
        args = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        args = None #the coder loop answers with "invalid argyments" and the model retries
    if not isinstance(args, dict):
        args = None  # valid JSON but not an object (a list, a string) is no use as arguments either
    return ToolCall(id=id, name=name, arguments=args, raw_arguments=raw)
