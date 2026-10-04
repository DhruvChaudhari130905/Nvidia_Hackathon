"""The room's live files: every save, by the coder or a person, goes through here (Q52).

A save checks `base_version`, stores the blob, emits `file.changed` and only then updates the live manifest,
so the event log, checkpoints, rewind, the code view and the coder all see the same files and versions.
Versions are the manifest's numbers (v1, v2, ...), never content hashes.

The room actor owns one `RoomFiles` per room and supplies `emit`, which stamps the seq, stores the event and
broadcasts it. Soft locks (§9) are the actor's job and are checked before calling `save`.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from mux.events.models import FileChanged
from mux.files import store
from mux.files.manifest import LiveFiles, Manifest, diff_summary

Emit = Callable[[str, dict], Awaitable[None]]  # (event type, payload)


class InvalidPath(ValueError):
    """A path would escape the project directory."""


def check_path(path: str) -> str:
    """Relative, with no empty, `.` or `..` segments: model-written paths can't leave the project."""
    if not path or path.startswith("/") or any(s in ("", ".", "..") for s in path.split("/")):
        raise InvalidPath(path)
    return path


@dataclass(frozen=True)
class SaveResult:
    """`ok` False means `base_version` was stale and nothing changed; `version` is then the current one."""

    ok: bool
    path: str
    version: int | None
    changed: bool = False


def _text(data: bytes) -> str | None:
    """UTF-8 text, or None for binary content."""
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


class RoomFiles:
    """Live files of one room, backed by the blob store."""

    def __init__(
        self,
        live: LiveFiles,
        emit: Emit,
        *,
        put_blob: Callable[[bytes], Awaitable[str]] = store.put,
        get_blob: Callable[[str], Awaitable[bytes]] = store.get,
    ) -> None:
        self.live = live
        self._emit = emit
        self._put_blob = put_blob
        self._get_blob = get_blob
        self._lock = asyncio.Lock()  # check-then-write must not interleave between the coder and a person

    @property
    def manifest(self) -> Manifest:
        """A copy of the live manifest (what a build or checkpoint uses)."""
        return dict(self.live.manifest)

    def version(self, path: str) -> int | None:
        """The live version of `path`, or None if it does not exist."""
        entry = self.live.manifest.get(path)
        return entry.version if entry else None

    async def read(self, path: str) -> tuple[bytes, int]:
        """Bytes and version of a live file; raises KeyError if absent."""
        entry = self.live.manifest[check_path(path)]
        return await self._get_blob(entry.hash), entry.version

    async def save(self, path: str, data: bytes | None, base_version: int | None, actor: str) -> SaveResult:
        """Write `data` (None deletes) if `base_version` is current (None: the file must not exist yet)."""
        check_path(path)
        async with self._lock:
            current = self.live.manifest.get(path)
            current_version = current.version if current else None
            if base_version != current_version:
                return SaveResult(False, path, current_version)
            if data is None and current is None:
                return SaveResult(True, path, None)
            old = await self._get_blob(current.hash) if current else b""
            new_hash = await self._put_blob(data) if data is not None else None
            if current is not None and new_hash == current.hash:
                return SaveResult(True, path, current.version)  # same content after normalising: no new version
            hw = self.live.high_water.get(path, 0)
            version = hw if new_hash is None else hw + 1
            new = store.normalize(data) if data is not None else b""  # what put_blob stored
            old_text, new_text = _text(old), _text(new)
            summary = diff_summary(old_text, new_text) if old_text is not None and new_text is not None else "binary file"
            payload = FileChanged(
                path=path, hash=new_hash, version=version, base_version=base_version,
                deleted=new_hash is None, actor=actor, diff_summary=summary,
            )
            await self._emit("file.changed", payload.model_dump(mode="json"))  # log first: if it fails, nothing changed
            self.live.apply_file_changed(payload)
            return SaveResult(True, path, version if new_hash else None, changed=True)
