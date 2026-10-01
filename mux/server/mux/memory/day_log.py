"""Compacts task logs into one day log when a sitting ends. Summarizes current state and rolls from day to day."""
from __future__ import annotations

from mux.agents.llm import LLM, ModelRole, Usage
from mux.memory.pins import merge_pins
from mux.memory.task_log import Log, LogDraft, LogResult, render_log, write_log

DAY_LOG_SYSTEM = """You keep the memory of a coding agent that builds a web app for a team. A work session just ended. Compact the logs below into one log of the current state. The next session starts from this log alone.

- "app": what the app is and what works now, at most 3 sentences.
- "changed": the main features the app has so far, at most 8 short lines, most important first.
- "open_threads": unfinished work, known bugs, and promises to the team, at most 6 lines. Drop threads a later log closed.
- "conventions": names, file layout, and style rules the code follows, at most 8 lines.
When logs disagree, the later log wins. Keep the whole log under 2400 characters. Team decisions are pinned separately, so leave them out.

Answer with JSON only:
{"app": "...", "changed": ["..."], "open_threads": ["..."], "conventions": ["..."]}"""

async def write_day_log(
        llm: LLM,
        previous_day: Log | None,
        task_logs: list[Log],
        *,
        role: ModelRole = ModelRole.SUPER, #Super until lightning spike passes
) -> LogResult:
    if not task_logs:
    # nothing was built this sitting, so the previous day log still holds
        return LogResult(previous_day or Log(LogDraft(app="Nothing built yet.")), Usage(), 0)

    pins = merge_pins(previous_day.pins if previous_day else [], *(log.pins for log in task_logs))
    sections = [f"Previous day log:\n{render_log(previous_day.draft, [])}"] if previous_day else []
    sections += [f"Task log {i}:\n{render_log(log.draft, [])}" for i, log in enumerate(task_logs, start=1)]
    # the latest task log already rolls forward everything before it
    return await write_log(llm, role, DAY_LOG_SYSTEM, "\n\n".join(sections), pins, task_logs[-1].draft)