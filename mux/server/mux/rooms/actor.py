"""RoomActor: owns one room's state and applies every change one at a time.

Every change is an event. The actor writes the event, plus any rows that go with it, in one Emitter
transaction, and updates its in-memory state only after the commit. Permission checks are the API's job.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mux.agents.coordinator.conflicts import Tally, Vote, tally, vote_weight

from mux.checkpoints import checkpoint, rewind
from mux.checkpoints.checkpoint import CheckpointRow, LogRow
from mux.db.session import get_sessionmaker
from mux.events import log
from mux.events.models import (
    ConflictClosed, ConflictDomain, ConflictEvidence, ConflictOpened, ConflictVote, CoordinatorReply, DomainRole,
    AgentText, EventEnvelope, EvidenceCitation, FileLockChanged, LinkAccess, LogWritten, MemberJoined, MemberPermission,
    MemberRoleChanged, MessageLabel, MessageLabeled, MessagePosted, MessageTo, Permission, PlanItem, PlanItems,
    PlanItemUpdated, PlanStatus, QuestionAnswered, QuestionDefaulted, QuestionOpened, RoomCreated,
    SharingChanged, TaskRef,
    PresenceJoined, PresenceLeft, PresenceTab, PresenceTyping, RoomPaused, SittingEnded, Tab,
)
from mux.files import manifest, store
from mux.files.manifest import LiveFiles
from mux.files.room_files import RoomFiles, SaveResult, check_path
from mux.files.template import load_template
from mux.rooms import plan as plans
from mux.rooms import records
from mux.rooms import budget as budgets
from mux.rooms.cards import QUESTION_S, RESEARCH_TIMEOUT_S, VOTE_S, Cards, Conflict, Question
from mux.rooms.emitter import Batch, Emitter, Publish
from mux.rooms.records import Member, RoomRecord


LOCK_IDLE_S = 120
SITTING_IDLE_S = 30 * 60  # a sitting ends when nobody has been connected for 30 minutes
TICK_S = 10  # how often the background tick runs
RECENT_MESSAGES = 20  # chat messages kept for the coordinator's view of the room

logger = logging.getLogger(__name__)

class FileLockError(PermissionError):
    """Someone else holds the file's lock, or the saver does not hold it."""

@dataclass
class FileLock:
    """A soft lock for manual editing. Kept in memory only (Q47): a rebuilt actor starts with none."""

    user_id: UUID
    touched: float # time.monotonic() of the last lock or save

@dataclass(frozen=True)
class Presence:
    """Who is connected. Never stored: it is rebuilt from live connections."""
    user_id: UUID
    name: str | None
    connections: int = 1 # open sockets; a user with two tabs leaves when the last one closes
    tab: Tab | None = None
    typing: bool = False

@dataclass
class RecentMessage:
    """A recent chat message and the coordinator's label for it (None until labeled, and for team messages)."""
    message: MessagePosted
    label: MessageLabel | None = None
    task_id: str | None = None  # the task it was queued or merged into

class RoomActor:
    """One room's state. Methods hold the actor lock, so changes apply one at a time."""

    def __init__(
        self,
        record: RoomRecord,
        emitter: Emitter,
        plan: plans.Plan = (),
        live: LiveFiles | None = None,
        *,
        checkpoints: dict[UUID, CheckpointRow] | None = None,
        head_seq: int = 0,
        budget: budgets.Budget | None = None,
        recent: dict[UUID, RecentMessage] | None = None,
        cards: Cards | None = None,
    ) -> None:
        self.record = record
        self.emitter = emitter
        self.wakeup = asyncio.Event()  # set when the plan or the budget changes, so the coder looks for work
        self.plan = plan
        self.files = RoomFiles(
            live or LiveFiles(), self._emit_file, put_blob=self._put_blob, get_blob=self.get_blob
        )
        self.budget = budget or budgets.Budget()
        self.presence: dict[UUID, Presence] = {}
        self.sitting_active = False  # a sitting starts when someone connects
        self.empty_since: float | None = None  # monotonic time the last person left, while a sitting is on
        self.on_sitting_end: Callable[[str], Awaitable[None]] | None = None  # part F: writes the day log
        self._ticker: asyncio.Task[None] | None = None
        self.locks: dict[str, FileLock] = {}
        self.edit_notes: list[str] = []  # manual edits the coder hears about at its next turn boundary (part F)
        self.recent: dict[UUID, RecentMessage] = recent or {}
        self.cards = cards or Cards()
        self.on_agent_message: Callable[[MessagePosted], None] | None = None  # the coordinator's queue
        self.interrupt_requested = False  # set by an 'interrupt' message; the coder stops at its next turn boundary (F3)
        self.checkpoints: dict[UUID, CheckpointRow] = checkpoints or {}
        # Seq of the latest head change (checkpoint.created or room.rewound): the next checkpoint's start_seq (R4)
        self.head_seq = head_seq
        self._lock = asyncio.Lock()

    @property
    def room_id(self) -> UUID:
        return self.record.id

    @property
    def plan(self) -> plans.Plan:
        return self._plan

    @plan.setter
    def plan(self, value: plans.Plan) -> None:
        self._plan = value
        self.wakeup.set()

    @classmethod
    async def create(
        cls,
        owner_id: UUID,
        title: str,
        publish: Publish,
        *,
        description: str = "",
        domain_role: DomainRole | None = None,
        template: Mapping[str, bytes] | None = None,
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    ) -> "RoomActor":
        """Create a room in one transaction: its row, the owner's membership, 'room.created', and checkpoint C0
        from the starter template (tests pass `template` instead)."""
        maker = sessionmaker or get_sessionmaker()
        files = load_template() if template is None else template
        room_id = uuid4()
        emitter = Emitter(room_id, 0, publish, sessionmaker=maker)
        async with emitter.transaction() as tx:
            record = await records.create(
                owner_id, title, description, domain_role, room_id=room_id, session=tx.session
            )
            await tx.emit(
                "room.created", RoomCreated(owner_id=owner_id, title=title, description=description), str(owner_id)
            )
            event = tx.reserve("checkpoint.created", str(owner_id))
            c0 = await checkpoint.create_root(room_id, files, event, session=tx.session)
            tx.stored(event.model_copy(update={"payload": checkpoint.created_payload(c0)}))
            root = await manifest.load(c0.manifest_id, session=tx.session)
        live = LiveFiles(manifest=dict(root), high_water={path: entry.version for path, entry in root.items()})
        actor = cls(record, emitter, live=live)
        actor._new_head(c0)
        return actor

    @classmethod
    async def open(
        cls, room_id: UUID, publish: Publish, *, sessionmaker: async_sessionmaker[AsyncSession] | None = None
    ) -> "RoomActor | None":
        """Load an existing room and replay its plan and files, or None if it does not exist."""
        maker = sessionmaker or get_sessionmaker()
        async with maker() as s:
            record = await records.load(room_id, session=s)
            if record is None:
                return None
            events = await log.read_all(room_id, session=s)
            checkpoints = await checkpoint.load_all(room_id, session=s)
            budget = await budgets.load(room_id, session=s)
            live = await LiveFiles.replay(events, lambda manifest_id: manifest.load(manifest_id, session=s))
        plan: plans.Plan = ()
        cards = Cards()
        for event in events:
            if event.type == "room.rewound":  # the plan jumps to the checkpoint's, like the files do
                plan = plans.load(checkpoints[UUID(event.payload["checkpoint_id"])].plan)
            else:
                plan = plans.apply(plan, event.type, event.payload)
            cards.apply(event.type, event.payload, event.ts)
        last_seq = events[-1].seq if events else 0
        head_seq = max((e.seq for e in events if e.type in rewind.HEAD_CHANGES), default=0)
        return cls(record, Emitter(room_id, last_seq, publish, sessionmaker=maker), plan, live,
                   checkpoints=checkpoints, head_seq=head_seq, budget=budget, recent=_recent_messages(events), cards=cards)

    def role_of(self, user_id: UUID) -> Permission | None:
        """The user's permission in this room, or None if they have no access."""
        return self.record.role_of(user_id)

    async def lock_file(self, path: str, user_id: UUID) -> None:
        """Take (or refresh) the soft lock on a file. Raises FileLockError if someone else holds it."""
        check_path(path)
        async with self._lock:
            await self._expire_locks()
            held = self.locks.get(path)
            if held and held.user_id != user_id:
                raise FileLockError(f"{path} is being edited by {held.user_id}")
            if held is None:
                await self.emitter.emit("file.locked", FileLockChanged(path=path, user_id=user_id), str(user_id))
            self.locks[path] = FileLock(user_id, time.monotonic())

    async def unlock_file(self, path: str, user_id: UUID, *, force: bool = False) -> bool:
        """Release a lock. Only its holder can, unless `force` (the API sets it for the owner).
        False if the file was not locked."""
        async with self._lock:
            held = self.locks.get(path)
            if held is None:
                return False
            if held.user_id != user_id and not force:
                raise FileLockError(f"{path} is locked by {held.user_id}")
            await self._release(path, held, str(user_id))
            return True

    async def release_user_locks(self, user_id: UUID) -> None:
        """Release every lock the user holds"""
        async with self._lock:
            await self._release_locks_of(user_id)

    async def _release_locks_of(self, user_id:UUID) -> None:
        """release_user_locks for a caller that holds the actor lock."""
        for path, held in list(self.locks.items()):
            if held.user_id == user_id:
                await self._release(path, held, str(user_id))

    async def save_file(self, path: str, content: bytes | None, base_version: int | None, user_id: UUID) -> SaveResult:
        """Save a manual edit (None deletes). The saver must hold the lock. A stale base_version changes nothing:
    the result then has ok=False and the current version."""
        async with self._lock:
            await self._expire_locks()
            held = self.locks.get(path)
            if held is None or held.user_id != user_id:
                raise FileLockError(f"take the lock on {path} before saving")
            self.locks[path] = FileLock(user_id, time.monotonic())
            result = await self.files.save(path, content, base_version, str(user_id))
            if result.changed:
                before = f"v{base_version}" if base_version is not None else "new"
                after = f"v{result.version}" if result.version is not None else "deleted"
                self.edit_notes.append(f"{user_id} edited {path} ({before} -> {after})")
            return result

    async def read_file(self, path: str) -> tuple[bytes, int]:
        """A live file's bytes and version. Raises KeyError if it does not exist."""
        return await self.files.read(path)

    async def _expire_locks(self) -> None:
        """Release locks idle longer than LOCK_IDLE_S. The caller holds the actor lock."""
        now = time.monotonic()
        for path, held in list(self.locks.items()):
            if now - held.touched > LOCK_IDLE_S:
                await self._release(path, held, "system")

    async def _release(self, path: str, held: FileLock, by: str) -> None:
        await self.emitter.emit("file.unlocked", FileLockChanged(path = path, user_id=held.user_id), by)
        del self.locks[path]

    async def _emit_file(self, type: str, payload: dict) -> None:
        """RoomFiles' emit. The saver recorded in the payload is the event's actor."""
        await self.emitter.emit(type, payload, payload["actor"])

    async def _put_blob(self, data: bytes) -> str:
        async with self.emitter.sessionmaker() as s, s.begin():
            return await store.put(data, session=s)

    async def get_blob(self, hash: str) -> bytes:
        async with self.emitter.sessionmaker() as s:
            return await store.get(hash, session=s)

    async def set_member(
        self, user_id: UUID, permission: MemberPermission, by: UUID, domain_role: DomainRole | None = None
    ) -> None:
        """Add a member or change their permission (the API checks that `by` is the owner)."""
        async with self._lock:
            old = self.record.members.get(user_id)
            async with self.emitter.transaction() as tx:
                await records.set_member(self.room_id, user_id, permission, domain_role, session=tx.session)
                if old is None:
                    payload = MemberJoined(user_id=user_id, permission=permission, domain_role=domain_role)
                    await tx.emit("member.joined", payload, str(by))
                else:
                    await tx.emit("member.role_changed", MemberRoleChanged(user_id=user_id, permission=permission), str(by))
            kept_role = domain_role if domain_role is not None else (old.domain_role if old else None)
            self._set_members({**self.record.members, user_id: Member(permission, kept_role)})

    async def join(self, user_id: UUID, domain_role: DomainRole | None = None) -> Permission:
        """Open the room. A member gets their permission back; in a room open to anyone, a new user becomes
        a member with the link's permission. Raises PermissionError for a private room."""
        async with self._lock:
            member = self.record.members.get(user_id)
            if member:
                return member.permission
            permission = self.record.link_permission
            if self.record.link_access != "anyone" or permission is None:
                raise PermissionError("this room is private; ask the owner to add you")
            async with self.emitter.transaction() as tx:
                await records.set_member(self.room_id, user_id, permission, domain_role, session=tx.session)
                payload = MemberJoined(user_id=user_id, permission=permission, domain_role=domain_role)
                await tx.emit("member.joined", payload, str(user_id))
            self._set_members({**self.record.members, user_id: Member(permission, domain_role)})
            return permission

    async def set_sharing(self, link_access: LinkAccess, link_permission: MemberPermission | None, by: UUID) -> None:
        """Change who can open the room by link (the API checks that `by` is the owner)."""
        async with self._lock:
            stored = link_permission if link_access == "anyone" else None
            async with self.emitter.transaction() as tx:
                await records.set_sharing(self.room_id, link_access, link_permission, session=tx.session)
                await tx.emit("sharing.changed", SharingChanged(link_access=link_access, link_permission=stored), str(by))
            self.record = replace(self.record, link_access=link_access, link_permission=stored)

    async def post_message(self, user_id: UUID, text: str, to: MessageTo = "agent") -> MessagePosted:
        """Store and broadcast a chat message. A message to the agent goes on to the coordinator."""
        message = MessagePosted(id=uuid4(), user_id=user_id, text=text, to=to)
        async with self._lock:
            await self.emitter.emit("message.posted", message, str(user_id))
            _remember(self.recent, message)
        if to == "agent" and self.on_agent_message is not None:
            self.on_agent_message(message)
        return message

    async def label_message(
        self, message_id: UUID, label: MessageLabel, rationale: str,
        domain: ConflictDomain | None = None, *, fallback: bool = False, task_id: str | None = None,
    ) -> None:
        """Store the coordinator's decision on a message, and the task it went into."""
        payload = MessageLabeled(
            message_id=message_id, label=label, rationale=rationale, domain=domain, fallback=fallback, task_id=task_id
        )
        async with self._lock:
            await self.emitter.emit("message.labeled", payload, "agent")
            if message_id in self.recent:
                self.recent[message_id].label = label
                self.recent[message_id].task_id = task_id

    async def reply(self, text: str, message_id: UUID | None = None) -> None:
        """The coordinator answers in the chat."""
        async with self._lock:
            await self.emitter.emit("coordinator.reply", CoordinatorReply(text=text, message_id=message_id), "agent")

    def unhandled(self) -> list[MessagePosted]:
        """Messages to the agent with no label yet: the server stopped before the coordinator got to them."""
        return [r.message for r in self.recent.values() if r.message.to == "agent" and r.label is None]

    async def draft_plan(self, items: list[PlanItem], by: str) -> None:
        """The first plan (from the coordinator or the owner). Replaces any plan there was."""
        await self._change_plan("plan.drafted", PlanItems(items=items).model_dump(mode="json"), by)

    async def edit_plan(self, items: list[PlanItem], by: str) -> None:
        """Replace the whole plan (the plan editor, or the coordinator inserting a task mid-plan)."""
        await self._change_plan("plan.edited", PlanItems(items=items).model_dump(mode="json"), by)

    async def approve_plan(self, by: str) -> None:
        """Draft tasks become todo (the API checks that `by` is the owner)."""
        await self._change_plan("plan.approved", {}, by)

    async def add_plan_item(self, item: PlanItem, by: str) -> None:
        """Append one task to the end of the plan."""
        await self._change_plan("plan.item_added", item.model_dump(mode="json"), by)

    async def update_plan_item(self, task_id: str, changes: dict[str, Any], by: str) -> None:
        """Change some fields of one task."""
        await self._change_plan("plan.item_updated", PlanItemUpdated(id=task_id, changes=changes).model_dump(mode="json"), by)

    async def add_note(self, task_id: str, note: str, by: str = "agent") -> None:
        """Append a merged note to a task, reading and writing under the lock so no other note is lost."""
        async with self._lock:
            item = self._task(task_id)
            notes = PlanItemUpdated(id=task_id, changes={"merged_notes": [*item.merged_notes, note]})
            await self._write([("plan.item_updated", notes)], by)

    async def split_task(self, task_id: str, titles: list[str], by: str = "agent") -> list[str]:
        """The coder splits its task: the task keeps its id and takes the first title, and the others
        follow it as new todo tasks. Returns the ids in order."""
        async with self._lock:
            item = self._task(task_id)
            first = int(plans.next_id(self.plan)[1:])
            ids = [task_id, *(f"t{first + n}" for n in range(len(titles) - 1))]
            new = [PlanItem(id=i, title=t[:200], status="todo") for i, t in zip(ids[1:], titles[1:])]
            at = self.plan.index(item)
            items = [*self.plan[:at], item.model_copy(update={"title": titles[0][:200]}), *new, *self.plan[at + 1:]]
            await self._write([("plan.edited", PlanItems(items=items))], by)
            return ids

    async def block_task(self, task_id: str, reason: str) -> None:
        """The coder gave up on its task. It waits as 'blocked' until a person sets it back to todo."""
        async with self._lock:
            item = self._task(task_id)
            changes = {"status": "blocked", "merged_notes": [*item.merged_notes, f"Blocked: {reason}"]}
            text = f'I stopped working on "{item.title}": {reason}. Set the task back to todo to try again.'
            await self._write([("plan.item_updated", PlanItemUpdated(id=task_id, changes=changes)),
                               ("coordinator.reply", CoordinatorReply(text=text))], "agent")

    def take_edit_notes(self) -> list[str]:
        """The manual-edit notes since the last call (the coder hears about them at its turn boundary)."""
        notes, self.edit_notes = self.edit_notes, []
        return notes

    async def log_event(self, type: str, payload: BaseModel, by: str = "agent") -> None:
        """Store one event that changes no state: the coder's text, tool calls and build results."""
        async with self._lock:
            await self.emitter.emit(type, payload, by)

    async def broadcast_text(self, task_id: str, text: str) -> None:
        """Stream a piece of the coder's text ('agent.text.delta', never stored)."""
        await self.emitter.broadcast("agent.text.delta", AgentText(task_id=task_id, text=text), "agent")

    def _task(self, task_id: str) -> PlanItem:
        item = next((item for item in self.plan if item.id == task_id), None)
        if item is None:
            raise ValueError(f"no task {task_id!r} in the plan")
        return item

    async def start_task(self, task_id: str, by: str = "agent") -> None:
        await self._change_plan("task.started", TaskRef(task_id=task_id).model_dump(mode="json"), by)

    async def finish_task(self, task_id: str, by: str = "agent") -> None:
        await self._change_plan("task.finished", TaskRef(task_id=task_id).model_dump(mode="json"), by)

    async def _change_plan(self, type: str, payload: dict[str, Any], by: str) -> None:
        """Check the change with plans.apply first (a broken rule raises before anything is written), then store it."""
        async with self._lock:
            new = plans.apply(self.plan, type, payload)
            await self.emitter.emit(type, payload, by)
            self.plan = new

    async def save_checkpoint(
        self, by: str, *, snapshot_uuid: str | None = None, log_body: str | None = None, pins: list | None = None
    ) -> CheckpointRow:
        """Checkpoint the live files and plan as a child of the head, with the task log if given.
        It becomes the new head (called after every finished task)."""
        async with self._lock:
            async with self.emitter.transaction() as tx:
                manifest_id = await manifest.save(self.room_id, self.files.manifest, session=tx.session)
                event = tx.reserve("checkpoint.created", by)
                cp = CheckpointRow(
                    id=uuid4(), room_id=self.room_id, seq=event.seq, start_seq=self.head_seq,
                    parent_id=self.record.head_checkpoint_id, manifest_id=manifest_id,
                    sandbox_snapshot_uuid=snapshot_uuid, plan=[item.model_dump(mode="json") for item in self.plan],
                )
                task_log = None
                if log_body is not None:
                    task_log = LogRow(id=uuid4(), kind="task", body=log_body, pins=pins or [], checkpoint_id=cp.id)
                row = await checkpoint.save(cp, task_log, event, session=tx.session)
                tx.stored(event.model_copy(update={"payload": checkpoint.created_payload(row)}))
                if task_log is not None:
                    await tx.emit("log.task_written", LogWritten(log_id=task_log.id, checkpoint_id=cp.id), by)
            self._new_head(row)
            return row

    async def save_day_log(self, body: str, pins: list) -> LogRow:
        """Store the day log on the head checkpoint (the sitting-end hook writes it)."""
        async with self._lock:
            head = self.record.head_checkpoint_id
            if head is None:
                raise ValueError("the room has no checkpoint")
            async with self.emitter.transaction() as tx:
                row = await checkpoint.save_log(
                    LogRow(id=uuid4(), kind="day", body=body, pins=pins, checkpoint_id=head), self.room_id,
                    session=tx.session,
                )
                await tx.emit("log.day_written", LogWritten(log_id=row.id, checkpoint_id=head), "agent")
            return row

    async def logs(self) -> tuple[LogRow | None, list[LogRow]]:
        """The head's log (the nearest on the path to the root, task or day), and every log of the room."""
        async with self.emitter.sessionmaker() as s:
            logs = await checkpoint.load_logs(self.room_id, session=s)
        head = self.record.head_checkpoint_id
        current = rewind.head_state(head, self.checkpoints, logs).log if head is not None else None
        return current, logs

    async def rewind_to(self, checkpoint_id: UUID, by: str) -> rewind.HeadState:
        """Move the head to a checkpoint (back or forward): its files, plan and log become current at once.
        Later events stay in the log and the UI greys them out. Raises KeyError for an unknown checkpoint."""
        async with self._lock:
            target = self.checkpoints[checkpoint_id]
            async with self.files.lock:  # no save may land between computing the versions and applying them
                async with self.emitter.transaction() as tx:
                    logs = await checkpoint.load_logs(self.room_id, session=tx.session)
                    state = rewind.head_state(target.id, self.checkpoints, logs)
                    files = await manifest.load(state.manifest_id, session=tx.session)
                    payload = rewind.rewound_payload(self.files.live, target.id, files)
                    event = await tx.emit("room.rewound", payload, by)
                    await records.set_head(self.room_id, target.id, session=tx.session)
                self.files.live.apply_rewound(payload, files)
            self.plan = plans.load(target.plan)
            self.record = replace(self.record, head_checkpoint_id=target.id)
            self.head_seq = event.seq
            return state


    # ---- conflict and question cards ----

    async def open_conflict(
        self, message_ids: list[UUID], summary: str, options: list[str], domain: ConflictDomain, title: str
    ) -> Conflict:
        """Open a conflict card. The todo tasks of the clashing messages wait (skipped_conflict) for the vote;
        when there are none, a new waiting task named `title` carries the result."""
        async with self._lock:
            linked = {self.recent[m].task_id for m in message_ids if m in self.recent}
            held = [item.id for item in self.plan if item.id in linked and item.status == "todo"]
            changes: list[tuple[str, BaseModel]] = [
                ("plan.item_updated", PlanItemUpdated(id=task_id, changes={"status": "skipped_conflict"}))
                for task_id in held
            ]
            if not held:
                new = PlanItem(id=plans.next_id(self.plan), title=title[:200], status="skipped_conflict")
                changes.append(("plan.item_added", new))
                held = [new.id]
            opened = ConflictOpened(
                id=uuid4(), message_ids=message_ids, summary=summary, options=options, domain=domain, task_ids=held
            )
            await self._write([("conflict.opened", opened), *changes], "agent")
            return self.cards.conflicts[opened.id]

    async def start_vote(
        self, conflict_id: UUID, summary: str | None = None, citations: list[EvidenceCitation] | None = None,
        queries: list[str] | None = None, *, now: datetime | None = None,
    ) -> None:
        """Attach the research (if any) and open the vote for VOTE_S. Ignored if the vote is already open."""
        async with self._lock:
            conflict = self.cards.open_conflict(conflict_id)
            if conflict.expires_at is None:
                await self._start_vote(conflict, summary, citations or [], queries or [], now or _now())

    async def vote(self, conflict_id: UUID, user_id: UUID, option: str) -> None:
        """Vote (again) on an open conflict. Once every editor and the owner has voted, the vote closes."""
        async with self._lock:
            conflict = self.cards.open_conflict(conflict_id)
            if option not in conflict.options:
                raise ValueError(f"{option!r} is not one of the options")
            weight = vote_weight(self._domain_role(user_id), conflict.domain)
            payload = ConflictVote(conflict_id=conflict_id, user_id=user_id, option=option, weight=weight)
            await self._write([("conflict.vote", payload)], str(user_id))
            voters = {uid for uid, m in self.record.members.items() if m.permission in ("owner", "editor")}
            if voters <= set(conflict.votes):
                await self._settle(conflict)

    async def override(self, conflict_id: UUID, option: str, by: UUID) -> None:
        """The owner picks the result (the API checks that `by` is the owner)."""
        async with self._lock:
            conflict = self.cards.open_conflict(conflict_id)
            if option not in conflict.options:
                raise ValueError(f"{option!r} is not one of the options")
            await self._close_conflict(conflict, option, "override", self._tally(conflict).totals, str(by))

    async def open_question(
        self, task_id: str | None, text: str, options: list[str], default: str, *, now: datetime | None = None
    ) -> Question:
        """The coder asks the room. Its task waits (skipped_question) until an answer or QUESTION_S pass."""
        if default not in options:
            raise ValueError("the default must be one of the options")
        async with self._lock:
            task = next((item for item in self.plan if item.id == task_id), None)
            if task_id is not None and task is None:
                raise ValueError(f"no task {task_id!r} in the plan")
            changes: list[tuple[str, BaseModel]] = []
            if task is not None and task.status in ("todo", "doing"):
                changes.append(("plan.item_updated", PlanItemUpdated(id=task.id, changes={"status": "skipped_question"})))
            expires_at = (now or _now()) + timedelta(seconds=QUESTION_S)
            opened = QuestionOpened(
                id=uuid4(), task_id=task_id, text=text, options=options, default=default, expires_at=expires_at
            )
            await self._write([("question.opened", opened), *changes], "agent")
            return self.cards.questions[opened.id]

    async def answer_question(self, question_id: UUID, answer: str, user_id: UUID) -> None:
        """An editor or the owner answers; the task goes back to the plan with the answer as a note."""
        async with self._lock:
            question = self.cards.open_question(question_id)
            if answer not in question.options:
                raise ValueError(f"{answer!r} is not one of the options")
            note = f'The room answered "{question.text}": {answer}'
            payload = QuestionAnswered(question_id=question_id, answer=answer, user_id=user_id)
            await self._write([("question.answered", payload), *self._resume_tasks(question, note)], str(user_id))

    async def _start_vote(
        self, conflict: Conflict, summary: str | None, citations: list[EvidenceCitation], queries: list[str],
        now: datetime,
    ) -> None:
        payload = ConflictEvidence(
            conflict_id=conflict.id, summary=summary, citations=citations, queries=queries,
            expires_at=now + timedelta(seconds=VOTE_S),
        )
        await self._write([("conflict.evidence", payload)], "agent")

    async def _settle(self, conflict: Conflict) -> None:
        """Close the vote by the tally. A tie stays open, and the owner is asked once to override (Q48)."""
        result = self._tally(conflict)
        if result.winner is not None:
            await self._close_conflict(conflict, result.winner, result.decided_by, result.totals, "system")
        elif not conflict.owner_asked:
            conflict.owner_asked = True
            text = f'The vote on "{conflict.summary}" is tied. The owner can pick an option to settle it.'
            await self._write([("coordinator.reply", CoordinatorReply(text=text))], "agent")

    async def _close_conflict(
        self, conflict: Conflict, result: str, resolved_by: str, totals: dict[str, int], by: str
    ) -> None:
        note = f'The team chose "{result}" for: {conflict.summary}'
        closed = ConflictClosed(conflict_id=conflict.id, result=result, resolved_by=resolved_by, totals=totals)
        await self._write([("conflict.closed", closed), *self._resume_tasks(conflict, note)], by)

    def _tally(self, conflict: Conflict) -> Tally:
        votes = [Vote(str(user_id), option, self._domain_role(user_id)) for user_id, option in conflict.votes.items()]
        return tally(conflict.options, votes, conflict.domain, str(self.record.owner_id))

    def _resume_tasks(self, card: Conflict | Question, note: str) -> list[tuple[str, BaseModel]]:
        """Plan changes that put a card's waiting tasks back, with the outcome as a merged note.
        They go back as drafts while the plan awaits approval."""
        waiting: PlanStatus = "skipped_conflict" if isinstance(card, Conflict) else "skipped_question"
        task_ids = card.task_ids if isinstance(card, Conflict) else [card.task_id]
        back: PlanStatus = "draft" if any(item.status == "draft" for item in self.plan) else "todo"
        return [
            ("plan.item_updated", PlanItemUpdated(
                id=item.id, changes={"status": back, "merged_notes": [*item.merged_notes, note]}
            ))
            for item in self.plan if item.id in task_ids and item.status == waiting
        ]

    async def _expire_cards(self, now: datetime) -> None:
        """Open votes whose research never came, close expired votes, default unanswered questions.
        The caller holds the actor lock."""
        for conflict in [c for c in self.cards.conflicts.values() if c.open]:
            if conflict.expires_at is None:
                if now - conflict.opened_at > timedelta(seconds=RESEARCH_TIMEOUT_S):
                    await self._start_vote(conflict, None, [], [], now)
            elif now >= conflict.expires_at:
                await self._settle(conflict)
        for question in [q for q in self.cards.questions.values() if q.open and now >= q.expires_at]:
            note = f'Nobody answered "{question.text}" in time, so the default is used: {question.default}'
            payload = QuestionDefaulted(question_id=question.id, answer=question.default)
            await self._write([("question.defaulted", payload), *self._resume_tasks(question, note)], "system")

    def _domain_role(self, user_id: UUID) -> DomainRole | None:
        member = self.record.members.get(user_id)
        return member.domain_role if member else None

    async def _write(self, changes: list[tuple[str, BaseModel]], by: str) -> None:
        """Store events in one transaction, then apply them to the plan and the cards. The caller holds the
        actor lock. Plan rules are checked first, so a broken rule raises before anything is written."""
        plan = self.plan
        for type, payload in changes:
            plan = plans.apply(plan, type, payload.model_dump(mode="json"))
        async with self.emitter.transaction() as tx:
            stored = [await tx.emit(type, payload, by) for type, payload in changes]
        self.plan = plan
        for event in stored:
            self.cards.apply(event.type, event.payload, event.ts)

    # ---- budget ----

    @property
    def paused(self) -> bool:
        """True while a budget cap is reached. The coder does not start work then (part F)."""
        return self.budget.over is not None

    async def charge(self, tokens: int = 0, runs: int = 0, by: str = "agent") -> None:
        """Record spent tokens and sandbox runs. They are already spent, so they always count;
        reaching a cap pauses the room."""
        if tokens < 0 or runs < 0:
            raise ValueError("usage cannot be negative")
        if tokens == 0 and runs == 0:
            return
        async with self._lock:
            new = replace(self.budget, tokens_used=self.budget.tokens_used + tokens, runs_used=self.budget.runs_used + runs)
            async with self.emitter.transaction() as tx:
                await budgets.add_usage(self.room_id, tokens, runs, session=tx.session)
                await self._emit_budget(tx, new, by)
            self.budget = new

    async def set_budget_caps(self, tokens_cap: int, runs_cap: int, by: str) -> None:
        """New caps (the API checks that `by` is the owner). Caps above the usage resume a paused room;
        caps below it pause the room."""
        if tokens_cap < 1 or runs_cap < 1:
            raise ValueError("caps must be at least 1")
        async with self._lock:
            new = replace(self.budget, tokens_cap=tokens_cap, runs_cap=runs_cap)
            async with self.emitter.transaction() as tx:
                await budgets.set_caps(self.room_id, tokens_cap, runs_cap, session=tx.session)
                await self._emit_budget(tx, new, by)
            self.budget = new
            self.wakeup.set()  # a resumed room has work for the coder again

    async def _emit_budget(self, tx: Batch, new: budgets.Budget, by: str) -> None:
        """'budget.updated', plus 'room.paused' or 'room.resumed' when the room crosses a cap."""
        await tx.emit("budget.updated", new.payload(), by)
        if new.over and not self.budget.over:
            await tx.emit("room.paused", RoomPaused(reason=new.over), by)
        elif self.budget.over and not new.over:
            await tx.emit("room.resumed", {}, by)

    # ---- presence ----

    async def connect(self, user_id: UUID, name: str | None = None) -> None:
        """A socket opened. A user's first connection announces them and starts a sitting if none is on."""
        async with self._lock:
            current = self.presence.get(user_id)
            if current is not None:
                self.presence[user_id] = replace(current, connections=current.connections + 1)
                return
            self.presence[user_id] = Presence(user_id, name)
            self.sitting_active = True
            self.empty_since = None
            joined = PresenceJoined(user_id=user_id, name=name, tab=None, typing=False)
            await self.emitter.broadcast("presence.join", joined, str(user_id))

    async def disconnect(self, user_id: UUID) -> None:
        """A socket closed. When the user's last connection is gone they leave, and their file locks are released."""
        async with self._lock:
            current = self.presence.get(user_id)
            if current is None:
                return
            if current.connections > 1:
                self.presence[user_id] = replace(current, connections=current.connections - 1)
                return
            del self.presence[user_id]
            await self.emitter.broadcast("presence.leave", PresenceLeft(user_id=user_id), str(user_id))
            await self._release_locks_of(user_id)
            if not self.presence and self.sitting_active:
                self.empty_since = time.monotonic()

    async def set_tab(self, user_id: UUID, tab: Tab) -> None:
        """The user switched tabs. Ignored for users who are not connected, and for no change."""
        async with self._lock:
            current = self.presence.get(user_id)
            if current is None or current.tab == tab:
                return
            self.presence[user_id] = replace(current, tab=tab)
            await self.emitter.broadcast("presence.tab", PresenceTab(user_id=user_id, tab=tab), str(user_id))

    async def set_typing(self, user_id: UUID, typing: bool) -> None:
        """The user started or stopped typing. Ignored for users who are not connected, and for no change."""
        async with self._lock:
            current = self.presence.get(user_id)
            if current is None or current.typing == typing:
                return
            self.presence[user_id] = replace(current, typing=typing)
            await self.emitter.broadcast("presence.typing", PresenceTyping(user_id=user_id, typing=typing), str(user_id))

    # ---- sitting and the background tick ----

    async def end_session(self, by: UUID) -> bool:
        """The owner ends the sitting (the API checks it is the owner). False if no sitting is on."""
        async with self._lock:
            ended = await self._end_sitting("owner", str(by))
        if ended:
            await self._sitting_ended("owner")
        return ended

    async def tick(self, now: datetime | None = None) -> None:
        """Housekeeping, every TICK_S: expire idle locks, close expired votes and questions, and end the
        sitting once nobody has been connected for SITTING_IDLE_S."""
        async with self._lock:
            await self._expire_locks()
            await self._expire_cards(now or _now())
            idle = self.empty_since is not None and time.monotonic() - self.empty_since > SITTING_IDLE_S
            ended = idle and await self._end_sitting("idle", "system")
        if ended:
            await self._sitting_ended("idle")

    def start(self) -> None:
        """Start the background tick (the registry calls this). Calling it twice is harmless."""
        if self._ticker is None:
            self._ticker = asyncio.create_task(self._tick_forever(), name=f"room-{self.room_id}-tick")

    async def stop(self) -> None:
        """Stop the background tick (app shutdown)."""
        if self._ticker is not None:
            self._ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ticker
            self._ticker = None

    async def _tick_forever(self) -> None:
        while True:
            await asyncio.sleep(TICK_S)
            try:
                await self.tick()
            except Exception:
                logger.exception("Tick failed in room %s", self.room_id)

    async def _end_sitting(self, reason: Literal["idle", "owner"], by: str) -> bool:
        """Store 'sitting.ended'. The caller holds the actor lock. False if no sitting is on."""
        if not self.sitting_active:
            return False
        await self.emitter.emit("sitting.ended", SittingEnded(reason=reason), by)
        self.sitting_active = False
        self.empty_since = None
        return True

    async def _sitting_ended(self, reason: Literal["idle", "owner"]) -> None:
        """Run the sitting-end hook outside the actor lock: part F's day log calls the model, which takes seconds."""
        if self.on_sitting_end is None:
            return
        try:
            await self.on_sitting_end(reason)
        except Exception:
            logger.exception("Sitting-end hook failed in room %s", self.room_id)


    def _new_head(self, cp: CheckpointRow) -> None:
        """`cp` is the new head: remember it and start the next span after its seq."""
        self.record = replace(self.record, head_checkpoint_id=cp.id)
        self.checkpoints[cp.id] = cp
        self.head_seq = cp.seq

    def _set_members(self, members: dict[UUID, Member]) -> None:
        self.record = replace(self.record, members=members)


def _now() -> datetime:
    return datetime.now(UTC)


def _remember(recent: dict[UUID, RecentMessage], message: MessagePosted) -> None:
    """Add a message to `recent`, dropping the oldest past RECENT_MESSAGES (dicts keep insertion order)."""
    recent[message.id] = RecentMessage(message)
    while len(recent) > RECENT_MESSAGES:
        del recent[next(iter(recent))]


def _recent_messages(events: list[EventEnvelope]) -> dict[UUID, RecentMessage]:
    """The recent messages and their labels, rebuilt from the log."""
    recent: dict[UUID, RecentMessage] = {}
    for event in events:
        if event.type == "message.posted":
            _remember(recent, MessagePosted.model_validate(event.payload))
        elif event.type == "message.labeled":
            labeled = MessageLabeled.model_validate(event.payload)
            if labeled.message_id in recent:
                recent[labeled.message_id].label = labeled.label
                recent[labeled.message_id].task_id = labeled.task_id
    return recent
