"""Compact previous tool results to reduce coder context size."""

from __future__ import annotations

import json
from typing import Any

MAX_KEPT_CHARS = 120


def compact(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shrink everything the model has already acted on.

    Tool results from the latest turn stay in full, because the model has not read them yet.
    Older tool results become one-line stubs, and long string arguments in older tool calls
    (the content of write_file and edit_file) are replaced by their length.
    """
    result = [dict(message) for message in messages]
    last_assistant = max((i for i, m in enumerate(result) if m.get("role") == "assistant"), default=-1)

    for message in result[:last_assistant]:
        if message.get("role") == "tool":
            message["content"] = _stub(str(message.get("content", "")))
        elif message.get("role") == "assistant" and message.get("tool_calls"):
            message["tool_calls"] = [_compact_call(call) for call in message["tool_calls"]]

    return result


def _stub(content: str) -> str:
    content = " ".join(content.split())
    if len(content) <= MAX_KEPT_CHARS:
        return content
    return f"[previous tool result] {content[:100]}..."


def _compact_call(call: dict[str, Any]) -> dict[str, Any]:
    function = call.get("function", {})
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError:
        return call
    return {**call, "function": {**function, "arguments": json.dumps(_shorten(arguments))}}


def _shorten(value: Any) -> Any:
    # edit_file nests its long strings inside a list of {find, replace} objects
    if isinstance(value, str) and len(value) > MAX_KEPT_CHARS:
        return f"[{len(value)} characters omitted]"
    if isinstance(value, dict):
        return {key: _shorten(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shorten(item) for item in value]
    return value
