"""Build a fresh, cache-friendly coder context for every task."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_MAX_FILES = 3
DEFAULT_MAX_LINES = 400


@dataclass(frozen=True)
class RelevantFile:
    """A file included in the task context."""

    path: str
    content: str
    reason: str = ""


@dataclass
class CoderContext:
    """Inputs for one fresh coder context. The output puts the stable prefix first, then task details."""

    system_prompt: str = ""
    conventions: str = ""

    room_log: str = ""  # Log.body from mux.memory, pins included
    plan: str = ""
    current_task: str = ""
    repo_map: str = ""

    relevant_files: list[RelevantFile] = field(default_factory=list)
    task_files: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)

    merged_messages: list[str] = field(default_factory=list)
    edit_notes: list[str] = field(default_factory=list)

    max_files: int = DEFAULT_MAX_FILES
    max_lines: int = DEFAULT_MAX_LINES


def build_context(context: CoderContext) -> list[dict[str, Any]]:
    """Build a new message list, so nothing from one task leaks into the next.

    Order matters for prompt caching: the system message is identical for every task in a room.
    Tool definitions are not repeated here; they go to the model through the tools parameter.
    """
    messages: list[dict[str, Any]] = []

    stable = "\n\n".join(
        part for part in (
            context.system_prompt.strip(),
            f"CONVENTIONS.md\n{context.conventions.strip()}" if context.conventions.strip() else "",
        ) if part
    )
    if stable:
        messages.append({"role": "system", "content": stable})

    sections = [
        f"LATEST ROOM LOG\n{context.room_log.strip()}" if context.room_log.strip() else "",
        _plan_section(context.plan, context.current_task),
        f"REPOSITORY MAP\n{context.repo_map.strip()}" if context.repo_map.strip() else "",
        *(
            _file_section(file)
            for file in _select_relevant_files(
                context.relevant_files,
                requested={*context.task_files, *context.changed_files},
                max_files=context.max_files,
                max_lines=context.max_lines,
            )
        ),
        _list_section("MERGED MESSAGES", context.merged_messages),
        _list_section("MANUAL EDIT NOTES", context.edit_notes),
    ]
    messages.extend({"role": "user", "content": section} for section in sections if section)
    return messages


def _plan_section(plan: str, current_task: str) -> str:
    if not plan.strip() and not current_task.strip():
        return ""
    parts = ["PLAN"]
    if plan.strip():
        parts.append(plan.strip())
    if current_task.strip():
        parts.append(f"CURRENT TASK\n> {current_task.strip()}")
    return "\n".join(parts)


def _select_relevant_files(
        files: list[RelevantFile], *, requested: set[str], max_files: int, max_lines: int,
) -> list[RelevantFile]:
    """Task files and recently changed files first, at most max_files files and max_lines lines in total."""
    selected: list[RelevantFile] = []
    seen: set[str] = set()
    remaining = max_lines

    for file in sorted(files, key=lambda item: (item.path not in requested, item.path)):
        if len(selected) >= max_files or remaining <= 0:
            break
        if file.path in seen:
            continue
        lines = file.content.splitlines()
        content = "\n".join(lines[:remaining])
        if len(lines) > remaining:
            content += f"\n... ({len(lines) - remaining} more lines; use read_file for the rest)"
        selected.append(RelevantFile(file.path, content, file.reason))
        seen.add(file.path)
        remaining -= min(len(lines), remaining)

    return selected


def _file_section(file: RelevantFile) -> str:
    reason = f" ({file.reason})" if file.reason.strip() else ""
    return f"FILE: {file.path}{reason}\n```text\n{file.content}\n```"


def _list_section(title: str, items: list[str]) -> str:
    lines = [item.strip() for item in items if item.strip()]
    return f"{title}\n" + "\n".join(f"- {line}" for line in lines) if lines else ""
