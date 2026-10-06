"""Room settings and memberships in Postgres. Who can do what in a room is read from here, never from presence."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert


from mux.db.tables import Membership, Room
from mux.events.log import scoped
from mux.events.models import DomainRole, LinkAccess, MemberPermission, Permission


@dataclass(frozen=True)
class Member:
    """One person's access to a room."""

    permission: Permission
    domain_role: DomainRole  | None


@dataclass(frozen=True)
class RoomRecord:
    """A room's settings and members, a stored."""

    id: UUID
    owner_id: UUID
    title: str
    description: str
    link_access: LinkAccess
    link_permission: MemberPermission | None
    head_checkpoint_id: UUID | None
    members: dict[UUID, Member] = field(default_factory=dict)

    def role_of(self, user_id: UUID) -> Permission | None:
        """Membership first; oherwise link permission when the link is open to anyone."""
        member = self.members.get(user_id)
        if member:
            return member.permission
        if self.link_access == "anyone":
            return self.link_permission or "viewer"
        return None


@dataclass(frozen=True)
class RoomSummary:
    """One row of user's room list."""

    id: UUID
    title: str
    description: str
    permission: Permission
    created_at: datetime
    members: dict[UUID, Member] = field(default_factory=dict)
    tokens_cap: int | None = None  # None: the default cap
    runs_cap: int | None = None


async def create(
        owner_id: UUID,
        title: str,
        description: str = "",
        domain_role: DomainRole | None = None,
        *,
        room_id: UUID | None = None,
        session: AsyncSession | None = None,
) -> RoomRecord:
    """Insert the room and the owner's membership in one transaction"""
    room_id = room_id or uuid4()
    async with scoped(session) as s:
        s.add(Room(id=room_id, owner_id = owner_id, title= title, description=description, link_access="restricted"))
        await s.flush() #memberships.room_id reference the room
        s.add(Membership(room_id=room_id, user_id=owner_id, permission="owner", domain_role = domain_role))
        await s.flush()
    return RoomRecord(
        id=room_id, owner_id=owner_id, title=title, description=description,
        link_access="restricted", link_permission=None, head_checkpoint_id=None,
        members={owner_id: Member("owner", domain_role)},
    )


async def load(room_id: UUID, *, session: AsyncSession | None = None) -> RoomRecord | None:
    """The room with its members, or None if it does not exist"""
    async with scoped(session) as s:
        #populate_existingL the upserts below bypass the ORM, so obects already in the session can be stale
        room = await s.get(Room, room_id, populate_existing = True)
        if room is None:
            return None
        rows = await s.scalars(
            select(Membership).where(Membership.room_id == room_id).execution_options(populate_existing=True)
        )
        members = {
            m.user_id: Member(cast(Permission, m.permission), cast(DomainRole | None, m.domain_role)) for m in rows
        }
        return RoomRecord(
            id=room.id, owner_id = room.owner_id, title=room.title, description=room.description,
            link_access = cast(LinkAccess, room.link_access),
            link_permission= cast(MemberPermission | None, room.link_permission),
            head_checkpoint_id= room.head_checkpoint_id, members=members,
        )


async def set_member(
        room_id: UUID,
        user_id: UUID,
        permission: Permission,
        domain_role: DomainRole | None = None,
        *,
        session: AsyncSession | None = None,
) -> None:
    """Add a member or change their permissin. A None dimaine_role keeps the one they had"""
    if permission == "owner":
        raise ValueError("a room has one owner, set when it is created")
    async with scoped(session) as s:
        owner_id = await s.scalar(select(Room.owner_id).where(Room.id == room_id))
        if owner_id is None:
            raise KeyError(room_id)
        if user_id == owner_id:
            raise ValueError("the owner's permission cannot change")
        stmt = insert(Membership).values(
            room_id = room_id, user_id=user_id, permission=permission, domain_role=domain_role
        )
        await s.execute(stmt.on_conflict_do_update(
            index_elements=[Membership.room_id, Membership.user_id],
            set_={
                "permission":stmt.excluded.permission,
                "domain_role": func.coalesce(stmt.excluded.domain_role, Membership.domain_role),
            },
        ))


async def set_sharing(
        room_id: UUID,
        link_access: LinkAccess,
        link_permission: MemberPermission | None,
        *,
        session: AsyncSession | None = None,
) -> None:
    """Who can open the room by sharing the link. 'restricted' means members only."""
    if link_access == "anyone":
        if link_permission not in("editor", "viewer"):
            raise ValueError("an open link needs link_permission 'editor' or 'viewer'.")
    elif link_access == "restricted":
        link_permission = None
    else:
        raise ValueError(f"unknown link_access {link_access!r}")
    async with scoped(session) as s:
        updated = await s.scalar(
            update(Room)
            .where(Room.id == room_id)
            .values(link_access=link_access, link_permission=link_permission)
            .returning(Room.id)
        )
        if updated is None:
            raise KeyError(room_id)


async def list_for_user(user_id: UUID, *, session: AsyncSession | None = None) -> list[RoomSummary]:
    """Rooms the user is a member of, newest first. A room open by link shows up once the user joins it."""
    async with scoped(session) as s:
        rows = (await s.execute(
            select(Room.id, Room.title, Room.description, Membership.permission, Room.created_at,
                   Room.budget_tokens_cap, Room.budget_runs_cap)
            .join(Membership, Membership.room_id == Room.id)
            .where(Membership.user_id == user_id)
            .order_by(Room.created_at.desc())
        )).all()
        members: dict[UUID, dict[UUID, Member]] = {r.id: {} for r in rows}
        found = await s.scalars(select(Membership).where(Membership.room_id.in_(members)))
        for m in found:
            members[m.room_id][m.user_id] = Member(cast(Permission, m.permission), cast(DomainRole | None, m.domain_role))
        return [
            RoomSummary(r.id, r.title, r.description, cast(Permission, r.permission), r.created_at, members[r.id],
                        r.budget_tokens_cap, r.budget_runs_cap)
            for r in rows
        ]


async def set_head(room_id: UUID, checkpoint_id: UUID, *, session: AsyncSession | None = None) -> None:
    """Move the room's head checkpoint (a rewind). New checkpoints move it in checkpoint.save."""
    async with scoped(session) as s:
        await s.execute(update(Room).where(Room.id == room_id).values(head_checkpoint_id=checkpoint_id))