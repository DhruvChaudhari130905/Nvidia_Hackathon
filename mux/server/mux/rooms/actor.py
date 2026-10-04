"""RoomActor: owns one room's state and applies every change one at a time.

Every change is an event. The actor writes the event, plus any rows that go with it, in one Emitter
transaction, and updates its in-memory state only after the commit. Permission checks are the API's job.
"""

import asyncio
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mux.db.session import get_sessionmaker
from mux.events import log
from mux.events.models import (
    DomainRole, LinkAccess, MemberJoined, MemberPermission, MemberRoleChanged, MessagePosted, MessageTo,
    Permission, PlanItem, PlanItems, PlanItemUpdated, RoomCreated, SharingChanged, TaskRef,
)
from mux.rooms import plan as plans
from mux.rooms import records
from mux.rooms.emitter import Emitter, Publish
from mux.rooms.records import Member, RoomRecord


class RoomActor:
    """One room's state. Methods hold the actor lock, so changes apply one at a time."""

    def __init__(self, record: RoomRecord, emitter: Emitter, plan: plans.Plan = ()) -> None:
        self.record = record
        self.emitter = emitter
        self.plan = plan
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
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    ) -> "RoomActor":
        """Create a room: its row, the owner's membership and 'room.created', in one transaction."""
        maker = sessionmaker or get_sessionmaker()
        room_id = uuid4()
        emitter = Emitter(room_id, 0, publish, sessionmaker=maker)
        async with emitter.transaction() as tx:
            record = await records.create(
                owner_id, title, description, domain_role, room_id=room_id, session=tx.session
            )
            await tx.emit(
                "room.created", RoomCreated(owner_id=owner_id, title=title, description=description), str(owner_id)
            )
        return cls(record, emitter)

    @classmethod
    async def open(
        cls, room_id: UUID, publish: Publish, *, sessionmaker: async_sessionmaker[AsyncSession] | None = None
    ) -> "RoomActor | None":
        """Load an existing room, or None if it does not exist. Replaying its plan and files comes in step 5."""
        maker = sessionmaker or get_sessionmaker()
        async with maker() as s:
            record = await records.load(room_id, session=s)
            if record is None:
                return None
            events = await log.read_all(room_id, session=s)
        plan: plans.Plan = ()
        for event in events:
            plan = plans.apply(plan, event.type, event.payload)
        last_seq = events[-1].seq if events else 0
        return cls(record, Emitter(room_id, last_seq, publish, sessionmaker=maker), plan)

    def role_of(self, user_id: UUID) -> Permission | None:
        """The user's permission in this room, or None if they have no access."""
        return self.record.role_of(user_id)

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

    def _set_members(self, members: dict[UUID, Member]) -> None:
        self.record = replace(self.record, members=members)
