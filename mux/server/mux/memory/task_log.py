"""Rolling task log (about 1 page), written after every task and stored with its checkpoint."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from mux.agents.coordinator.agent import ask_json
from mux.agents.coordinator.prompts import PlanItem
from mux.agents.llm import LLM, ModelRole, Usage
from mux.memory.pins import Pin, merge_pins, render_pins

LOG_CHAR_LIMIT = 2400 # about 600 tokens, not counting pins
PINS_HEADING = "Pinned team decisions (do not change these):"

TASK_LOG_SYSTEM = """You keep the memory of a coding agent that builds a web app for a team. After each task you rewrite the room log. The next task starts from this log alone, so it must hold everything that still matters.

Roll the previous log forward:
- "app": what the app is and what works now, at most 3 sentences.
- "changed": what this task changed, at most 8 short lines. Keep older changes only if they still matter.
- "open_threads": unfinished work, known bugs, and promises to the team, at most 6 lines. Remove threads this task closed.
- "conventions": names, file layout, and style rules the code follows, at most 8 lines.
Keep the whole log under 2400 characters. Team decisions are pinned separately, so leave them out.

Answer with JSON only:
{"app": "...", "changed": ["..."], "open_threads": ["..."], "conventions": ["..."]}"""

class LogDraft(BaseModel):
    app: str
    changed: list[str] = Field(default_factory=list, max_length=8)
    open_threads: list[str] = Field(default_factory=list, max_length=6)
    conventions: list[str] = Field(default_factory=list, max_length=8)

@dataclass
class Log:
    draft: LogDraft
    pins: list[Pin] = field(default_factory=list)

    @property
    def body(self) -> str:
        return render_log(self.draft, self.pins)

    @classmethod
    def stored(cls, body: str, pins: list[dict]) -> Log:
        """A log back from its stored body and pins. The sections are not split again: the whole text goes in
        `app`, which is enough for the next log to roll it forward."""
        text = body.split(PINS_HEADING)[0].strip()
        return cls(LogDraft(app=text.removeprefix("App: ")), [Pin(**pin) for pin in pins])

@dataclass
class LogResult:
    log : Log
    usage: Usage
    attempts: int
    fallback: bool = False #true when the model failed twice and the log was built without it

async def write_task_log(
        llm: LLM,
        previous: Log | None,
        task: PlanItem,
        changes: list[str],
        plan: list[PlanItem],
        new_pins: list[Pin] | None = None,
        *,
        role: ModelRole = ModelRole.SUPER,  # Super until the Lightning spike passes
) -> LogResult:
    pins = merge_pins(previous.pins if previous else [], new_pins or [])
    happened = "\n".join(f"- {c}" for c in changes) or "(nothing recorded)"
    plan_lines = "\n".join(f"- [{p.id}] {p.title} ({p.status})" for p in plan) or "(empty)"
    user = (
        f"Previous log:\n{render_log(previous.draft, []) if previous else '(none, this was the first task)'}\n\n"
        f"Task just finished: [{task.id}] {task.title}\n\n"
        f"What happened in this task:\n{happened}\n\n"
        f"Plan now:\n{plan_lines}"
    )
    old = previous.draft if previous else LogDraft(app=task.title)
    fallback = LogDraft(
        app = old.app,
        changed=[f"Finished: {task.title}", *changes][:8],
        open_threads=old.open_threads,
        conventions = old.conventions,
    )
    return await write_log(llm, role, TASK_LOG_SYSTEM, user, pins,fallback)

async def write_log(
    llm: LLM, role: ModelRole, system: str, user: str, pins: list[Pin], fallback: LogDraft,
) -> LogResult:
    """Shared by task and day logs: ask for a LogDraft under the size cap, else use the fallback."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    result = await ask_json(llm, role, messages, LogDraft, check=_too_long, max_tokens=900)
    if result.value is None:
        return LogResult(Log(fallback, pins), result.usage, result.attempts, fallback=True)
    return LogResult(Log(result.value, pins), result.usage, result.attempts)

def render_log(draft: LogDraft, pins: list[Pin]) -> str:
    parts = [f"App: {draft.app}"]
    for heading, items in (("Changed", draft.changed), ("Open threads", draft.open_threads), ("Conventions", draft.conventions)):
        if items:
            parts.append(f"{heading}:\n" + "\n".join(f"- {item}" for item in items))
    if pins:
            parts.append(f"{PINS_HEADING}\n" + render_pins(pins))
    return "\n\n".join(parts)

def _too_long(draft: LogDraft) -> str:
    size = len(render_log(draft, []))
    return f"the log is {size} characters, keep it under {LOG_CHAR_LIMIT}" if size > LOG_CHAR_LIMIT else ""
        