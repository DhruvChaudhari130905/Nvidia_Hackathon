"""RoomActor: owns one room's state and applies every change one at a time.

Every change is an event. The actor writes the event, plus any rows that go with it, in one Emitter
transaction, and updates its in-memory state only after the commit. Permission checks are the API's job.
"""


import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mux.checkpoints import checkpoint, rewind
from mux.checkpoints.checkpoint import CheckpointRow, LogRow
from mux.db.session import get_sessionmaker
from mux.events import log
from mux.events.models import (
    DomainRole, FileLockChanged, LinkAccess, MemberJoined, MemberPermission, MemberRoleChanged, MessagePosted,
    MessageTo, Permission, PlanItem, PlanItems, PlanItemUpdated, RoomCreated, SharingChanged, TaskRef,
)
from mux.files import manifest, store
from mux.files.manifest import LiveFiles
from mux.files.room_files import RoomFiles, SaveResult, check_path
from mux.files.template import load_template
from mux.rooms import plan as plans
from mux.rooms import records
from mux.rooms.emitter import Emitter, Publish
from mux.rooms.records import Member, RoomRecord


LOCK_IDLE_S = 120

class FileLockError(PermissionError):
    """Someone else holds the file's lock, or the saver does not hold it."""

@dataclass
class FileLock:
    """A soft lock for manual editing. Kept in memory only (Q47): a rebuilt actor starts with none."""

    user_id: UUID
    touched: float # time.monotonic() of the last lock or save

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
    ) -> None:
        self.record = record
        self.emitter = emitter
        self.plan = plan
        self.files = RoomFiles(live or LiveFiles(), self._emit_file, put_blob=self._put_blob, get_blob = self._get_blob)
        self.locks: dict[str, FileLock] = {}
        self.edit_notes: list[str] = [] # manual edits the coder hears about at its next turn boundary (part F)
        self.checkpoints: dict[UUID, CheckpointRow] = checkpoints or {}
        # Seq of the latest head change (checkpoint.created or room.rewound): the next checkpoint's start_seq (R4)
        self.head_seq = head_seq
        self._lock = asyncio.Lock()

    @property
    def room_id(self) -> UUID:
        return self.record.id

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
            live = await LiveFiles.replay(events, lambda manifest_id: manifest.load(manifest_id, session=s))
        plan: plans.Plan = ()
        for event in events:
            plan = plans.apply(plan, event.type, event.payload)
        last_seq = events[-1].seq if events else 0
        head_seq = max((e.seq for e in events if e.type in rewind.HEAD_CHANGES), default=0)
        return cls(record, Emitter(room_id, last_seq, publish, sessionmaker=maker), plan, live,
                   checkpoints=checkpoints, head_seq=head_seq)
    
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
        """Release every lock the user holds (their last connection closed)."""
        async with self._lock:
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

    async def _get_blob(self, hash: str) -> bytes:
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
        """Store and broadcast a chat message. Routing it to the coordinator comes later (part F)."""
        message = MessagePosted(id=uuid4(), user_id=user_id, text=text, to=to)
        async with self._lock:
            await self.emitter.emit("message.posted", message, str(user_id))
        return message

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
                    task_log = LogRow(id=uuid4(), kind="task", body=log_body, pins=pins or [], checkpoint_id =cp.id)
                row = await checkpoint.save(cp, task_log, event, session=tx.session)
                tx.stored(event.model_copy(update={"payload": checkpoint.created_payload(row)}))
            self._new_head(row)
            return row
    
    def _new_head(self, cp: CheckpointRow) -> None:
        """`cp` is the new head: remember it and start the next span after its seq."""
        self.record = replace(self.record, head_checkpoint_id=cp.id)
        self.checkpoints[cp.id] = cp
        self.head_seq = cp.seq

    def _set_members(self, members: dict[UUID, Member]) -> None:
        self.record = replace(self.record, members=members)
