"""Room settings and memberships: create, load, members, sharing, and a user's room list."""

from uuid import uuid4

import pytest

from mux.rooms import records


async def test_create_load_roundtrip(db_session):
    owner = uuid4()
    created = await records.create(owner, "Todo app", "a small todo app", "pm", session=db_session)
    loaded = await records.load(created.id, session=db_session)
    assert loaded == created
    assert loaded is not None
    assert loaded.members == {owner: records.Member("owner", "pm")}
    assert (loaded.link_access, loaded.link_permission) == ("restricted", None)


async def test_load_unknown_room(db_session):
    assert await records.load(uuid4(), session=db_session) is None


async def test_role_of(db_session):
    owner, editor, stranger = uuid4(), uuid4(), uuid4()
    room = await records.create(owner, "r", session=db_session)
    await records.set_member(room.id, editor, "editor", session=db_session)
    loaded = await records.load(room.id, session=db_session)
    assert loaded is not None
    assert loaded.role_of(owner) == "owner"
    assert loaded.role_of(editor) == "editor"
    assert loaded.role_of(stranger) is None

    await records.set_sharing(room.id, "anyone", "viewer", session=db_session)
    loaded = await records.load(room.id, session=db_session)
    assert loaded is not None
    assert loaded.role_of(stranger) == "viewer"
    assert loaded.role_of(editor) == "editor"  # membership beats the link


async def test_set_member_upserts_and_keeps_domain_role(db_session):
    room = await records.create(uuid4(), "r", session=db_session)
    user = uuid4()
    await records.set_member(room.id, user, "viewer", "design", session=db_session)
    await records.load(room.id, session=db_session)  # puts the membership in the session, so a stale read would show
    await records.set_member(room.id, user, "editor", session=db_session)
    loaded = await records.load(room.id, session=db_session)
    assert loaded is not None
    assert loaded.members[user] == records.Member("editor", "design")


async def test_set_member_rejects_owner_changes_and_unknown_room(db_session):
    owner = uuid4()
    room = await records.create(owner, "r", session=db_session)
    with pytest.raises(ValueError):
        await records.set_member(room.id, owner, "editor", session=db_session)
    with pytest.raises(ValueError):
        await records.set_member(room.id, uuid4(), "owner", session=db_session)
    with pytest.raises(KeyError):
        await records.set_member(uuid4(), uuid4(), "editor", session=db_session)


async def test_set_sharing_rules(db_session):
    room = await records.create(uuid4(), "r", session=db_session)
    with pytest.raises(ValueError):
        await records.set_sharing(room.id, "anyone", None, session=db_session)
    await records.set_sharing(room.id, "restricted", "editor", session=db_session)
    loaded = await records.load(room.id, session=db_session)
    assert loaded is not None
    assert (loaded.link_access, loaded.link_permission) == ("restricted", None)
    with pytest.raises(KeyError):
        await records.set_sharing(uuid4(), "restricted", None, session=db_session)


async def test_list_for_user_newest_first(db_session):
    a, b = uuid4(), uuid4()
    first = await records.create(a, "first", session=db_session)
    await db_session.commit()  # now() is fixed per transaction; commit so the rooms get different created_at
    second = await records.create(a, "second", session=db_session)
    await db_session.commit()
    shared = await records.create(b, "shared", session=db_session)
    await records.set_member(shared.id, a, "viewer", session=db_session)
    await db_session.commit()

    rows = await records.list_for_user(a, session=db_session)
    assert [(r.id, r.permission) for r in rows] == [
        (shared.id, "viewer"), (second.id, "owner"), (first.id, "owner"),
    ]
    assert await records.list_for_user(uuid4(), session=db_session) == []
