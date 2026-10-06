"""Runs the coordinator for one room: each message to the agent, one at a time, outside the actor lock.

The coordinator only decides (agents/coordinator). This worker builds its view of the room, charges the tokens,
stores the label, and carries out the decision through the actor like any other change.
"""

import asyncio
import contextlib
import logging
from uuid import UUID

from mux.agents.coordinator import prompts
from mux.agents.coordinator.agent import Coordinator
from mux.agents.coordinator.planner import create_plan
from mux.agents.coordinator.schema import AddPlanItem, CoordinatorAction
from mux.agents.llm import LLM
from mux.events.models import MessagePosted, PlanItem, PlanStatus
from mux.rooms import plan as plans
from mux.rooms.actor import RoomActor

MAX_PENDING = 8  # earlier requests the coordinator sees, to spot a clash with the new one

logger = logging.getLogger(__name__)


class RoomCoordinator:
    """The coordinator worker of one room. The registry starts one per actor when a model is configured."""

    def __init__(self, actor: RoomActor, llm: LLM) -> None:
        self.actor = actor
        self.llm = llm
        self.coordinator = Coordinator(llm)
        self.queue: asyncio.Queue[MessagePosted] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Take the actor's messages to the agent and start the worker. Messages left unlabeled when the
        server stopped go first. Calling it twice is harmless."""
        if self._worker is not None:
            return
        self.actor.on_agent_message = self.queue.put_nowait
        for message in self.actor.unhandled():
            self.queue.put_nowait(message)
        self._worker = asyncio.create_task(self._run(), name=f"room-{self.actor.room_id}-coordinator")

    async def stop(self) -> None:
        """Stop the worker (app shutdown). Messages still queued stay unlabeled and run on the next start."""
        self.actor.on_agent_message = None
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def _run(self) -> None:
        while True:
            message = await self.queue.get()
            try:
                await self.handle(message)
            except Exception:
                logger.exception("Coordinator failed on message %s in room %s", message.id, self.actor.room_id)
                with contextlib.suppress(Exception):
                    await self.actor.reply("Something went wrong with that message. Please send it again.", message.id)
            finally:
                self.queue.task_done()

    async def handle(self, message: MessagePosted) -> None:
        """Decide what one message means and carry it out. Model errors propagate to the worker."""
        actor = self.actor
        if actor.paused:
            # left unlabeled, so it runs again when the room is next opened
            await actor.reply(f"The room is paused: its {actor.budget.over} budget is used up. "
                              "The owner can raise the cap.", message.id)
            return
        if not actor.plan:
            await self._draft_plan(message)
            return
        view, new, _ = room_view(actor, message)
        decision = await self.coordinator.classify(view, new)
        await actor.charge(tokens=decision.usage.total)
        action = decision.action
        await actor.label_message(message.id, action.label, action.rationale, action.domain, fallback=decision.fallback)
        await self._apply(action, message)

    async def _draft_plan(self, message: MessagePosted) -> None:
        """The first message to a room with no plan: draft one from the room's description and the message."""
        description = "\n\n".join(text for text in (self.actor.record.description, message.text) if text.strip())
        result = await create_plan(self.llm, description)
        await self.actor.charge(tokens=result.usage.total)
        items = [
            PlanItem(id=item.id, title=item.title[:200], status="draft", owner_role=item.owner_role, notes=item.notes)
            for item in result.items
        ]
        await self.actor.label_message(
            message.id, "plan", "The room had no plan, so this message started one.", fallback=result.fallback
        )
        await self.actor.draft_plan(items, "agent")
        await self.actor.reply(
            f"I drafted a plan of {len(items)} tasks. Edit it if you like; the owner approves it to start.", message.id
        )

    async def _apply(self, action: CoordinatorAction, message: MessagePosted) -> None:
        if action.label == "chat":
            await self.actor.reply(action.reply or "", message.id)
        elif action.label == "queue" and action.add_plan_item is not None:
            await self._queue(action.add_plan_item)
        elif action.label in ("merge", "interrupt"):
            current = plans.current(self.actor.plan)
            if current is None:  # nothing in progress to merge into, so it becomes a task of its own
                await self._queue(AddPlanItem(title=message.text[:80]))
                return
            notes = [*current.merged_notes, message.text]
            await self.actor.update_plan_item(current.id, {"merged_notes": notes}, "agent")
            if action.label == "interrupt":
                self.actor.interrupt_requested = True
        elif action.label == "conflict" and action.open_conflict is not None:
            # F2 turns this into a conflict card with research and a vote
            conflict = action.open_conflict
            await self.actor.reply(
                f"This clashes with an earlier request: {conflict.summary} Options: {'; '.join(conflict.options)}.",
                message.id,
            )

    async def _queue(self, item: AddPlanItem) -> None:
        """Add a task after `after_task_id`, or at the end. It is a draft while the plan awaits approval."""
        plan = self.actor.plan
        status: PlanStatus = "draft" if any(p.status == "draft" for p in plan) else "todo"
        new = PlanItem(id=plans.next_id(plan), title=item.title[:200], status=status)
        ids = [p.id for p in plan]
        if item.after_task_id in ids[:-1]:
            at = ids.index(item.after_task_id) + 1
            await self.actor.edit_plan([*plan[:at], new, *plan[at:]], "agent")
        else:
            await self.actor.add_plan_item(new, "agent")


def room_view(actor: RoomActor, message: MessagePosted) -> tuple[prompts.RoomView, prompts.Message, dict[str, UUID]]:
    """The coordinator's view of the room and the new message. Messages get short ids (m1, m2, ...) that the
    model copies back; the returned dict maps them to the real message ids."""
    earlier = [r for r in actor.recent.values() if r.message.id != message.id]
    pending = [r.message for r in earlier if r.label in ("merge", "queue", "interrupt")][-MAX_PENDING:]
    team = [r.message for r in earlier if r.message.to == "team"][-prompts.MAX_TEAM_NOTES:]
    ids = {f"m{n}": m.id for n, m in enumerate([*pending, message], start=1)}
    short = {real: s for s, real in ids.items()}
    current = plans.current(actor.plan)
    view = prompts.RoomView(
        plan=[prompts.PlanItem(p.id, p.title, p.status, p.owner_role, p.notes) for p in actor.plan],
        current_task_id=current.id if current else None,
        pending=[_prompt_message(actor, m, short[m.id]) for m in pending],
        team_notes=[_prompt_message(actor, m, "") for m in team],
    )
    return view, _prompt_message(actor, message, short[message.id]), ids


def _prompt_message(actor: RoomActor, message: MessagePosted, short_id: str) -> prompts.Message:
    presence = actor.presence.get(message.user_id)
    member = actor.record.members.get(message.user_id)
    author = presence.name if presence and presence.name else f"user {str(message.user_id)[:8]}"
    return prompts.Message(short_id, author, member.domain_role if member else None, message.text)
