"""Tests for manifests, version stamps and diffs (files/manifest.py)."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mux.events.models import CheckpointCreated, EventEnvelope, FileChanged, RoomRewound
from mux.files import manifest as mf
from mux.files.manifest import Entry, LiveFiles, Manifest

ROOM = uuid4()
TS = datetime(2026, 10, 1, tzinfo=timezone.utc)


def ev(seq: int, type: str, payload: dict) -> EventEnvelope:
    return EventEnvelope(seq=seq, room_id=ROOM, type=type, actor="coder", ts=TS, payload=payload)


def changed(path: str, h: str | None, version: int, base: int | None) -> dict:
    return FileChanged(path=path, hash=h, version=version, base_version=base, deleted=h is None,
                       actor="coder", diff_summary="").model_dump(mode="json")


# ---- pure ----


def test_diff_added_removed_changed_sorted() -> None:
    a = {"b.ts": Entry("1", 1), "a.ts": Entry("1", 1), "keep.ts": Entry("k", 1)}
    b = {"keep.ts": Entry("k", 2), "a.ts": Entry("2", 2), "z.ts": Entry("1", 1), "c.ts": Entry("1", 1)}
    d = mf.diff(a, b)
    assert (d.added, d.removed, d.changed) == (["c.ts", "z.ts"], ["b.ts"], ["a.ts"])  # version-only change is not a change


def test_restore_versions_skips_unchanged_and_uses_high_water() -> None:
    live = {"same.ts": Entry("s", 4), "edit.ts": Entry("new", 7)}
    target = {"same.ts": Entry("s", 2), "edit.ts": Entry("old", 3), "gone.ts": Entry("g", 1)}
    # gone.ts was deleted live after reaching v5: its restored version must be above 5.
    assert mf.restore_versions(live, target, {"edit.ts": 7, "gone.ts": 5}) == {"edit.ts": 8, "gone.ts": 6}


def test_diff_summary_counts_and_caps() -> None:
    old = "\n".join(f"line {i}" for i in range(40))
    new = "\n".join(f"LINE {i}" for i in range(40))
    out = mf.diff_summary(old, new, max_lines=5).splitlines()
    assert out[0] == "+40 −40"
    assert len(out) == 6


def test_diff_summary_no_change() -> None:
    assert mf.diff_summary("a\n", "a\n") == "+0 −0"


def test_bump_versions_and_delete_keeps_high_water() -> None:
    live = LiveFiles()
    assert live.bump("a.ts", "h1") == 1
    assert live.bump("a.ts", "h2") == 2
    assert live.bump("a.ts", None) == 2
    assert "a.ts" not in live.manifest and live.high_water["a.ts"] == 2
    assert live.bump("a.ts", "h3") == 3  # re-created above the old high-water mark, never back to 1


def test_apply_file_changed_takes_recorded_version() -> None:
    live = LiveFiles()
    live.apply_file_changed(FileChanged.model_validate(changed("a.ts", "h", 9, 8)))
    assert live.manifest["a.ts"] == Entry("h", 9)
    live.apply_file_changed(FileChanged.model_validate(changed("a.ts", None, 10, 9)))
    assert "a.ts" not in live.manifest and live.high_water["a.ts"] == 10


async def test_replay_seeds_from_c0_then_applies_changes_and_rewind() -> None:
    m0, m1 = uuid4(), uuid4()
    manifests: dict[UUID, Manifest] = {
        m0: {"a.ts": Entry("a1", 1)},
        m1: {"a.ts": Entry("a2", 2), "b.ts": Entry("b1", 1)},
    }
    c0, c1 = uuid4(), uuid4()

    def created(cid: UUID, parent: UUID | None, mid: UUID, start: int) -> dict:
        return CheckpointCreated(checkpoint_id=cid, parent_id=parent, start_seq=start, manifest_id=mid,
                                 sandbox_snapshot_uuid=None).model_dump(mode="json")

    async def load(mid: UUID) -> Manifest:
        return manifests[mid]

    events = [
        ev(1, "checkpoint.created", created(c0, None, m0, 0)),
        ev(2, "file.changed", changed("a.ts", "a2", 2, 1)),
        ev(3, "file.changed", changed("b.ts", "b1", 1, None)),
        ev(4, "checkpoint.created", created(c1, c0, m1, 1)),
        ev(5, "file.changed", changed("a.ts", "a3", 3, 2)),
        ev(6, "room.rewound", RoomRewound(checkpoint_id=c0, versions={"a.ts": 4}).model_dump(mode="json")),
    ]
    live = await LiveFiles.replay(list(reversed(events)), load)  # order of the input does not matter
    assert live.manifest == {"a.ts": Entry("a1", 4)}  # b.ts removed by the rewind to C0
    assert live.high_water == {"a.ts": 4, "b.ts": 1}  # b.ts keeps its mark


# ---- Postgres ----


async def test_save_load_roundtrip(db_session: AsyncSession, room: UUID) -> None:
    m = {"src/App.tsx": Entry("h1", 3), "a b/ü.ts": Entry("h2", 1)}
    mid = await mf.save(room, m, session=db_session)
    assert await mf.load(mid, session=db_session) == m


async def test_empty_manifest_roundtrip(db_session: AsyncSession, room: UUID) -> None:
    mid = await mf.save(room, {}, session=db_session)
    assert await mf.load(mid, session=db_session) == {}


async def test_load_missing_raises_keyerror(db_session: AsyncSession, room: UUID) -> None:
    with pytest.raises(KeyError):
        await mf.load(uuid4(), session=db_session)
