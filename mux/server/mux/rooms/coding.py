"""Runs the coder for one room: the approved plan, one task at a time, outside the actor lock.

The coder never touches room state directly. Its file tools save through the actor's `RoomFiles`, its plan tool
and questions go through actor methods, and every model call and sandbox run is charged to the room's budget.
After each finished task it writes the task log and saves a checkpoint; when a sitting ends, the day log.
"""

import asyncio
import contextlib
import logging
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel

from mux.agents.coder.context import CoderContext, build_context
from mux.agents.coder.loop import CoderLoop, CoderResult, CoderTask, TurnBoundary
from mux.agents.coder.prompts import CODER_SYSTEM_PROMPT
from mux.agents.coder.tools import TOOL_SCHEMAS, CoderToolExecutor
from mux.agents.coder.tools.files import RoomFileTools
from mux.agents.coder.tools.plan import PlanTool
from mux.agents.coordinator import prompts
from mux.agents.coordinator.conflicts import Tally
from mux.agents.llm import LLM, DeltaCallback, LLMReply, ModelRole
from mux.events.models import AgentText, BuildResult, PlanItem, ToolCalled, ToolResult, TurnInterrupted
from mux.files.repo_map import format_repo_map, map_files
from mux.integrations.tavily import WebSearch
from mux.memory.day_log import write_day_log
from mux.memory.pins import Pin, pin_override, pin_vote
from mux.memory.task_log import Log, write_task_log
from mux.rooms import plan as plans
from mux.rooms.actor import RoomActor
from mux.sandbox.runner import Runner

ARGUMENT_CHARS = 200  # longer string arguments (file contents) are cut in 'tool.called'
SUMMARY_CHARS = 200
CONVENTIONS = "CONVENTIONS.md"

logger = logging.getLogger(__name__)


class RoomCoder:
    """The coder worker of one room. The registry starts one per actor when a model is configured."""

    def __init__(
        self, actor: RoomActor, llm: LLM, *, runner: Runner | None = None, search: WebSearch | None = None
    ) -> None:
        self.actor = actor
        self.llm = llm
        self.runner = runner  # None: run_build and run_tests answer that builds are not configured
        self.search = search
        self._worker: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start working through the plan, and write the day log when a sitting ends. Calling it twice is harmless."""
        if self._worker is not None:
            return
        self.actor.on_sitting_end = self.write_day_log
        self._worker = asyncio.create_task(self._run(), name=f"room-{self.actor.room_id}-coder")

    async def stop(self) -> None:
        """Stop the worker (app shutdown). A task in progress stays 'doing' and starts again on the next start."""
        self.actor.on_sitting_end = None
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def _run(self) -> None:
        while True:
            self.actor.wakeup.clear()
            item = next_task(self.actor)
            if item is None:
                await self.actor.wakeup.wait()  # the plan or the budget changed: look again
                continue
            try:
                await self.run_task(item)
            except Exception as e:
                logger.exception("Coder failed on task %s in room %s", item.id, self.actor.room_id)
                with contextlib.suppress(Exception):
                    await self.actor.block_task(item.id, f"an error stopped the work ({type(e).__name__})")
                await asyncio.sleep(1)  # if even blocking failed, do not spin on the same task

    async def run_task(self, item: PlanItem) -> CoderResult:
        """Run one task to its end: done, waiting for an answer, interrupted, or blocked."""
        actor = self.actor
        if item.status == "todo":
            await actor.start_task(item.id)
        tools = RoomTools(actor, item.id, CoderToolExecutor(
            RoomFileTools(actor.files, locked_by=lambda path: _holder(actor, path)),
            runner=self.runner, search=self.search,
            plan=PlanTool(item.id, actor.split_task),
            on_question=lambda card: actor.open_question(item.id, card["question"], card["options"], card["default"]),
        ))
        log = await self._current_log()
        boundary = Boundary(actor, item.id, delivered=len(item.merged_notes))
        loop = CoderLoop(
            ChargedLLM(self.llm, actor, item.id), tools, boundary, TOOL_SCHEMAS,
            on_text_delta=lambda text: actor.broadcast_text(item.id, text),
        )
        messages = await self._context(item, log, actor.take_edit_notes())
        result = await loop.run_task(CoderTask(item.id, item.title), messages)
        await self._after(result, tools, log, boundary.stopped_by)
        return result

    async def _after(self, result: CoderResult, tools: "RoomTools", log: Log | None, stopped_by: str | None) -> None:
        actor = self.actor
        item = next((i for i in actor.plan if i.id == result.task_id), None)
        if item is None or item.status != "doing":
            return  # the task now waits for an answer (ask_room), or a rewind or plan edit took it away
        if result.status == "done":
            await actor.finish_task(item.id)
            await self._task_log(item, tools, log)
        elif stopped_by is not None:
            # it stays 'doing' and starts again with a fresh context that includes the new notes
            await actor.log_event("turn.interrupted", TurnInterrupted(task_id=item.id, reason=stopped_by))
        else:
            await actor.block_task(item.id, result.summary)

    async def _task_log(self, item: PlanItem, tools: "RoomTools", previous: Log | None) -> None:
        """Roll the task log forward and checkpoint the files, the plan and the log."""
        actor = self.actor
        pinned = {pin.conflict_id for pin in previous.pins} if previous else set()
        new_pins = [pin for pin in conflict_pins(actor) if pin.conflict_id not in pinned]
        plan = [_prompt_item(i) for i in actor.plan]
        result = await write_task_log(self.llm, previous, _prompt_item(item), tools.changes, plan, new_pins)
        await actor.charge(tokens=result.usage.total)
        await actor.save_checkpoint(
            "agent", snapshot_uuid=tools.inner.snapshot_uuid, log_body=result.log.body,
            pins=[asdict(pin) for pin in result.log.pins],
        )

    async def write_day_log(self, reason: str) -> None:
        """The sitting-end hook: compact this sitting's task logs into one day log on the head checkpoint."""
        _, logs = await self.actor.logs()
        last_day = max((n for n, lg in enumerate(logs) if lg.kind == "day"), default=-1)
        task_logs = [Log.stored(lg.body, lg.pins) for lg in logs[last_day + 1:] if lg.kind == "task"]
        if not task_logs:
            return
        previous = Log.stored(logs[last_day].body, logs[last_day].pins) if last_day >= 0 else None
        result = await write_day_log(self.llm, previous, task_logs)
        await self.actor.charge(tokens=result.usage.total)
        await self.actor.save_day_log(result.log.body, [asdict(pin) for pin in result.log.pins])

    async def _current_log(self) -> Log | None:
        current, _ = await self.actor.logs()
        return Log.stored(current.body, current.pins) if current else None

    async def _context(self, item: PlanItem, log: Log | None, edit_notes: list[str]) -> list[dict[str, Any]]:
        texts = await _texts(self.actor)
        notes = f"\n{item.notes}" if item.notes else ""
        return build_context(CoderContext(
            system_prompt=CODER_SYSTEM_PROMPT,
            conventions=texts.get(CONVENTIONS, ""),
            room_log=log.body if log else "",
            plan="\n".join(f"- [{i.id}] {i.title} ({i.status})" for i in self.actor.plan),
            current_task=f"[{item.id}] {item.title}{notes}",
            repo_map=format_repo_map(map_files(texts)),
            merged_messages=list(item.merged_notes),
            edit_notes=edit_notes,
        ))


def next_task(actor: RoomActor) -> PlanItem | None:
    """The task to work on: the one in progress (after a restart or an interrupt), else the first todo.
    Nothing while the room is paused or the plan still awaits approval."""
    if actor.paused or any(item.status == "draft" for item in actor.plan):
        return None
    return plans.current(actor.plan) or next((item for item in actor.plan if item.status == "todo"), None)


def conflict_pins(actor: RoomActor) -> list[Pin]:
    """A pin for every closed vote: the result and how it was decided."""
    pins: list[Pin] = []
    for c in actor.cards.conflicts.values():
        if c.result is None:
            continue
        if c.resolved_by == "override":
            pins.append(pin_override(str(c.id), c.summary, c.result))
        else:
            pin = pin_vote(str(c.id), c.summary, Tally(c.result, c.totals, c.resolved_by or "votes"))
            if pin is not None:
                pins.append(pin)
    return pins


class Boundary:
    """The coder's turn boundary: new merged notes and manual-edit notes go in; an interrupt, a pause, or the
    task leaving 'doing' (a question, an edit) stops the task."""

    def __init__(self, actor: RoomActor, task_id: str, *, delivered: int) -> None:
        self.actor = actor
        self.task_id = task_id
        self.delivered = delivered  # merged notes already in the context
        self.stopped_by: str | None = None

    async def turn_boundary(self) -> TurnBoundary:
        actor = self.actor
        item = next((i for i in actor.plan if i.id == self.task_id), None)
        if item is None or item.status != "doing":
            self.stopped_by = "the task left the plan's work"
        elif actor.interrupt_requested:
            actor.interrupt_requested = False
            self.stopped_by = "a message changed the task"
        elif actor.paused:
            self.stopped_by = "the room is paused"
        if self.stopped_by is not None:
            return TurnBoundary(interrupt=True)
        assert item is not None
        merges = item.merged_notes[self.delivered:]
        self.delivered = len(item.merged_notes)
        return TurnBoundary(merges=tuple(merges), edit_notes=tuple(actor.take_edit_notes()))

    async def task_boundary(self, task_id: str, summary: str) -> None:
        """Nothing here: the runner finishes the task once the loop returns, when it knows how it ended."""


class ChargedLLM:
    """The coder's model: every reply is charged to the room, and its text stored as 'agent.text'."""

    def __init__(self, llm: LLM, actor: RoomActor, task_id: str) -> None:
        self.llm = llm
        self.actor = actor
        self.task_id = task_id

    async def chat(
        self, role: ModelRole, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None = None,
        schema: type[BaseModel] | None = None, reasoning: bool | None = None, max_tokens: int | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> LLMReply:
        reply = await self.llm.chat(role, messages, tools=tools, schema=schema, reasoning=reasoning,
                                    max_tokens=max_tokens, on_delta=on_delta)
        await self.actor.charge(tokens=reply.usage.total)
        if reply.text.strip():
            await self.actor.log_event("agent.text", AgentText(task_id=self.task_id, text=reply.text))
        return reply


class RoomTools:
    """The coder's tools, with every call and result stored as events and every sandbox run charged."""

    def __init__(self, actor: RoomActor, task_id: str, inner: CoderToolExecutor) -> None:
        self.actor = actor
        self.task_id = task_id
        self.inner = inner
        self.changes: list[str] = []  # what this task changed, for the task log

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        actor, task_id = self.actor, self.task_id
        await actor.log_event("tool.called", ToolCalled(task_id=task_id, name=name, arguments=_short(arguments)))
        result = await self.inner.execute(name, arguments)
        ok = bool(result.get("ok")) if isinstance(result, dict) else True
        if name in ("run_build", "run_tests") and self.inner.runner is not None:
            await actor.charge(runs=1)
            event = "build.result" if name == "run_build" else "test.result"
            await actor.log_event(event, BuildResult(
                task_id=task_id, passed=ok, errors=list(result.get("errors", []))[:5],
                snapshot_uuid=self.inner.snapshot_uuid if name == "run_build" else None,
            ))
            self.changes.append(f"{'Build' if name == 'run_build' else 'Tests'} {'passed' if ok else 'failed'}")
        else:
            summary = _summary(result)
            await actor.log_event("tool.result", ToolResult(task_id=task_id, name=name, ok=ok, summary=summary))
            if ok and name in ("write_file", "edit_file", "delete_file"):
                verb = {"write_file": "Created", "edit_file": "Edited", "delete_file": "Deleted"}[name]
                self.changes.append(f"{verb} {arguments.get('path')}")
        return result


def _holder(actor: RoomActor, path: str) -> str | None:
    lock = actor.locks.get(path)
    if lock is None:
        return None
    presence = actor.presence.get(lock.user_id)
    return presence.name if presence and presence.name else "a teammate"


async def _texts(actor: RoomActor) -> dict[str, str]:
    """The room's live text files (binary files are left out), for the repo map and CONVENTIONS.md."""
    texts: dict[str, str] = {}
    for path, entry in actor.files.manifest.items():
        with contextlib.suppress(UnicodeDecodeError):
            texts[path] = (await actor.get_blob(entry.hash)).decode("utf-8")
    return texts


def _prompt_item(item: PlanItem) -> prompts.PlanItem:
    return prompts.PlanItem(item.id, item.title, item.status, item.owner_role, item.notes)


def _short(arguments: dict[str, Any]) -> dict[str, Any]:
    return {k: v[:ARGUMENT_CHARS] + "…" if isinstance(v, str) and len(v) > ARGUMENT_CHARS else v
            for k, v in arguments.items()}


def _summary(result: Any) -> str:
    if isinstance(result, dict):
        if not result.get("ok", True):
            return str(result.get("error", "failed"))[:SUMMARY_CHARS]
        for key in ("path", "summary", "query"):
            if key in result:
                return str(result[key])[:SUMMARY_CHARS]
        return "ok"
    return str(result)[:SUMMARY_CHARS]

