"""Manifests (path to hash), version stamps, and diffs between manifests."""

import difflib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mux.db.tables import ManifestRow
from mux.events.log import scoped
from mux.events.models import CheckpointCreated, EventEnvelope, FileChanged, RoomId, RoomRewound


@dataclass(frozen=True)
class Entry:
    """One file in a manifest."""

    hash: str
    version: int


Manifest = dict[str, Entry]


@dataclass
class ManifestDiff:
    """Paths only (DB11), sorted."""

    added: list[str]
    removed: list[str]
    changed: list[str]


def diff(a: Manifest, b: Manifest) -> ManifestDiff:
    """Paths added, removed, or with a different hash going from `a` to `b`."""
    return ManifestDiff(
        added=sorted(b.keys() - a.keys()),
        removed=sorted(a.keys() - b.keys()),
        changed=sorted(p for p in a.keys() & b.keys() if a[p].hash != b[p].hash),
    )


def restore_versions(
    live: Manifest, target: Manifest, high_water: Mapping[str, int] | None = None
) -> dict[str, int]:
    """Versions for a rewind (DB4): each target path whose content changes gets high-water + 1.

    Paths with an unchanged hash are left out, so they keep their live version and a coder's
    `base_version` stays valid. Pass `LiveFiles.high_water` so deleted paths count too.
    """
    hw = high_water or {}
    return {
        p: max(hw.get(p, 0), live[p].version if p in live else 0) + 1
        for p, e in target.items()
        if p not in live or live[p].hash != e.hash
    }


def diff_summary(old: str, new: str, max_lines: int = 20) -> str:
    """`+N −M` line counts followed by a unified diff capped at `max_lines` lines (DB11)."""
    lines = [
        ln for ln in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=1)
        if not ln.startswith(("---", "+++"))
    ]
    plus = sum(ln.startswith("+") for ln in lines)
    minus = sum(ln.startswith("-") for ln in lines)
    return "\n".join([f"+{plus} −{minus}", *lines[:max_lines]])


@dataclass
class LiveFiles:
    """The room's live manifest plus per-path version high-water marks (DB4)."""

    manifest: Manifest = field(default_factory=dict)
    high_water: dict[str, int] = field(default_factory=dict)

    def bump(self, path: str, new_hash: str | None) -> int:
        """Record a live edit and return its version. None deletes the path, keeping its high-water mark."""
        if new_hash is None:
            self.manifest.pop(path, None)
            return self.high_water.get(path, 0)
        version = self.high_water.get(path, 0) + 1
        self.manifest[path] = Entry(new_hash, version)
        self.high_water[path] = version
        return version

    def apply_file_changed(self, p: FileChanged) -> None:
        """Replay a `file.changed`: take the recorded version, never recompute it (R2, R3)."""
        if p.deleted or p.hash is None:
            self.manifest.pop(p.path, None)
        else:
            self.manifest[p.path] = Entry(p.hash, p.version)
        self.high_water[p.path] = max(self.high_water.get(p.path, 0), p.version)

    def apply_rewound(self, p: RoomRewound, target: Manifest) -> None:
        """Replay a `room.rewound`: hashes from `target`, versions from the payload."""
        new: Manifest = {}
        for path, e in target.items():
            version = p.versions.get(path)
            if version is None:
                version = self.manifest[path].version if path in self.manifest else e.version
            new[path] = Entry(e.hash, version)
            self.high_water[path] = max(self.high_water.get(path, 0), version)
        self.manifest = new

    @classmethod
    async def replay(
        cls, events: Sequence[EventEnvelope], load_manifest: Callable[[UUID], Awaitable[Manifest]]
    ) -> "LiveFiles":
        """Rebuild from seq 0, applying every event, greyed or not (R3)."""
        live = cls()
        manifest_of: dict[UUID, UUID] = {}
        for e in sorted(events, key=lambda e: e.seq):
            if e.type == "checkpoint.created":
                cc = CheckpointCreated.model_validate(e.payload)
                manifest_of[cc.checkpoint_id] = cc.manifest_id
                if cc.parent_id is None and not live.manifest:  # C0 seeds the live manifest
                    live.manifest = dict(await load_manifest(cc.manifest_id))
                    live.high_water = {p: en.version for p, en in live.manifest.items()}
            elif e.type == "file.changed":
                live.apply_file_changed(FileChanged.model_validate(e.payload))
            elif e.type == "room.rewound":
                rr = RoomRewound.model_validate(e.payload)
                live.apply_rewound(rr, await load_manifest(manifest_of[rr.checkpoint_id]))
        return live


async def save(room_id: RoomId, m: Manifest, *, session: AsyncSession | None = None) -> UUID:
    """Persist a manifest (checkpoints only) and return its id."""
    mid = uuid4()
    async with scoped(session) as s:
        s.add(ManifestRow(id=mid, room_id=room_id, entries={p: {"hash": e.hash, "version": e.version} for p, e in m.items()}))
        await s.flush()
    return mid


async def load(manifest_id: UUID, *, session: AsyncSession | None = None) -> Manifest:
    """Load a manifest by id; raises KeyError if absent."""
    async with scoped(session) as s:
        entries = await s.scalar(select(ManifestRow.entries).where(ManifestRow.id == manifest_id))
    if entries is None:
        raise KeyError(manifest_id)
    return {p: Entry(v["hash"], v["version"]) for p, v in entries.items()}
