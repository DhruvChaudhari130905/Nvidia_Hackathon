"""Compact previous tool results to reduce coder context size."""

from __future__ import annotations

import json
from typing import Any

MAX_KEPT_CHARS = 120
# File contents the model keeps seeing after the turn it read them in. Without them it reads the same
# files again and again (it read two files in turn until the turn limit in room_f0c75b04aff2).
KEPT_READS_BUDGET = 60_000
_CHANGES = {"write_file", "edit_file", "delete_file"}


def compact(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shrink everything the model has already acted on.

    Tool results from the latest turn stay in full, because the model has not read them yet. The latest
    read of each file also stays in full (newest first, up to KEPT_READS_BUDGET characters) unless the
    file changed after it. Other older tool results become one-line stubs, and long string arguments in
    older tool calls (the content of write_file and edit_file) are replaced by their length.
    """
    result = [dict(message) for message in messages]
    last_assistant = max((i for i, m in enumerate(result) if m.get("role") == "assistant"), default=-1)
    calls = _calls_by_id(result)
    kept, why = _reads_to_keep(result, calls)

    for i, message in enumerate(result[:last_assistant]):
        if message.get("role") == "tool" and i not in kept:
            name, arguments = calls.get(str(message.get("tool_call_id", "")), ("", {}))
            if name == "read_file" and arguments.get("path"):
                message["content"] = f"[earlier read of {arguments['path']}: {why.get(i, 'dropped to save space')}; read it again if you need it]"
            else:
                message["content"] = _stub(str(message.get("content", "")))
        elif message.get("role") == "assistant" and message.get("tool_calls"):
            message["tool_calls"] = [_compact_call(call) for call in message["tool_calls"]]

    return result


def _calls_by_id(messages: list[dict[str, Any]]) -> dict[str, tuple[str, dict[str, Any]]]:
    calls: dict[str, tuple[str, dict[str, Any]]] = {}
    for message in messages:
        for call in message.get("tool_calls") or []:
            function = call.get("function", {})
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            calls[call.get("id", "")] = (function.get("name", ""), arguments if isinstance(arguments, dict) else {})
    return calls


def _succeeded(content: Any) -> bool:
    try:
        value = json.loads(content) if isinstance(content, str) else content
    except json.JSONDecodeError:
        return False
    return isinstance(value, dict) and value.get("ok", True) is not False


def _reads_to_keep(messages: list[dict[str, Any]], calls: dict[str, tuple[str, dict[str, Any]]]) -> tuple[set[int], dict[int, str]]:
    """Indexes of read_file results to keep in full, and why each other read was dropped."""
    kept: set[int] = set()
    why: dict[int, str] = {}
    changed_later: set[str] = set()
    seen: set[tuple[Any, ...]] = set()
    used = 0
    for i in range(len(messages) - 1, -1, -1):  # newest first
        message = messages[i]
        if message.get("role") != "tool":
            continue
        name, arguments = calls.get(str(message.get("tool_call_id", "")), ("", {}))
        path = arguments.get("path")
        if not path:
            continue
        if name in _CHANGES and _succeeded(message.get("content")):
            changed_later.add(path)
        elif name == "read_file":
            key = (path, arguments.get("start_line"), arguments.get("end_line"))
            size = len(str(message.get("content", "")))
            if path in changed_later:
                why[i] = "the file changed after this read"
            elif key in seen:
                why[i] = "a newer read of it is further down"
            elif used + size > KEPT_READS_BUDGET:
                why[i] = "dropped to save space"
            else:
                kept.add(i)
                used += size
            seen.add(key)
    return kept, why


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
