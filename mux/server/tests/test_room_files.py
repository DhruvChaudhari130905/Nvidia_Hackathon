"""Tests for the room's live files and the coder tools on top of them (Q51, Q52)."""

from pathlib import Path

import pytest

from mux.agents.coder.tools import CoderToolExecutor
from mux.agents.coder.tools.files import FileTools, RoomFileTools
from mux.events.models import FileChanged
from mux.files import store
from mux.files.manifest import Entry, LiveFiles
from mux.files.room_files import InvalidPath, RoomFiles
from mux.replay.fake_sandbox import FakeSandbox
from mux.sandbox.client import RunResult
from mux.sandbox.runner import BUILD_CMD, TEST_CMD, Runner, wrap


class Room:
    """In-memory blobs and an event list, standing in for Postgres and the actor."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.blobs: dict[str, bytes] = {}
        self.events: list[tuple[str, dict]] = []
        live = LiveFiles()
        for path, data in (files or {}).items():
            h = store.hash_bytes(store.normalize(data))
            self.blobs[h] = store.normalize(data)
            live.manifest[path] = Entry(h, 1)
            live.high_water[path] = 1
        self.files = RoomFiles(live, self.emit, put_blob=self.put, get_blob=self.get)

    async def put(self, data: bytes) -> str:
        data = store.normalize(data)
        h = store.hash_bytes(data)
        self.blobs[h] = data
        return h

    async def get(self, h: str) -> bytes:
        return self.blobs[h]

    async def emit(self, type: str, payload: dict) -> None:
        self.events.append((type, payload))


def app_room() -> Room:
    return Room({"src/App.tsx": b"const a = 1;\nconst b = 1;\n"})


# ---- RoomFiles ----


async def test_save_emits_file_changed_with_version_and_diff() -> None:
    room = app_room()
    res = await room.files.save("src/App.tsx", b"const a = 2;\nconst b = 1;\n", 1, "user-1")
    assert (res.ok, res.version, res.changed) == (True, 2, True)
    [(type, payload)] = room.events
    p = FileChanged.model_validate(payload)
    assert (type, p.path, p.version, p.base_version, p.actor, p.deleted) == ("file.changed", "src/App.tsx", 2, 1, "user-1", False)
    assert p.diff_summary.startswith("+1 −1")


async def test_stale_base_changes_nothing() -> None:
    room = app_room()
    res = await room.files.save("src/App.tsx", b"x", 7, "coder")
    assert (res.ok, res.version) == (False, 1)
    assert room.events == [] and room.files.version("src/App.tsx") == 1


async def test_same_content_is_not_a_new_version() -> None:
    room = app_room()
    res = await room.files.save("src/App.tsx", b"const a = 1;\r\nconst b = 1;\r\n", 1, "coder")  # CRLF only
    assert (res.ok, res.version, res.changed) == (True, 1, False)
    assert room.events == []


async def test_delete_then_recreate_goes_above_old_version() -> None:
    room = app_room()
    await room.files.save("src/App.tsx", b"v2", 1, "coder")
    deleted = await room.files.save("src/App.tsx", None, 2, "coder")
    assert (deleted.ok, deleted.version) == (True, None)
    assert FileChanged.model_validate(room.events[-1][1]).deleted
    again = await room.files.save("src/App.tsx", b"new", None, "coder")
    assert again.version == 3


async def test_events_replay_to_the_same_live_files() -> None:
    room = app_room()
    start = LiveFiles(dict(room.files.live.manifest), dict(room.files.live.high_water))
    await room.files.save("src/App.tsx", b"two", 1, "coder")
    await room.files.save("src/Nav.tsx", b"nav", None, "user-1")
    await room.files.save("src/App.tsx", None, 2, "coder")
    for _, payload in room.events:
        start.apply_file_changed(FileChanged.model_validate(payload))
    assert (start.manifest, start.high_water) == (room.files.live.manifest, room.files.live.high_water)


async def test_failed_emit_leaves_files_unchanged() -> None:
    room = app_room()

    async def broken(type: str, payload: dict) -> None:
        raise RuntimeError("db down")

    room.files._emit = broken
    with pytest.raises(RuntimeError):
        await room.files.save("src/App.tsx", b"x", 1, "coder")
    assert room.files.version("src/App.tsx") == 1


async def test_bad_paths_refused() -> None:
    with pytest.raises(InvalidPath):
        await app_room().files.save("../x", b"x", None, "coder")


# ---- coder tools on the room ----


def room_executor(room: Room, results: dict | None = None) -> tuple[CoderToolExecutor, FakeSandbox]:
    fake = FakeSandbox(results or {})
    runner = Runner(fake, room.get, image="mux-starter")
    return CoderToolExecutor(RoomFileTools(room.files), runner=runner), fake


async def test_coder_edit_goes_through_the_room() -> None:
    room = app_room()
    tools, _ = room_executor(room)
    read = await tools.execute("read_file", {"path": "src/App.tsx"})
    assert read["version"] == 1
    ok = await tools.execute(
        "edit_file", {"path": "src/App.tsx", "base_version": 1, "edits": [{"find": "b = 1", "replace": "b = 2"}]}
    )
    assert (ok["ok"], ok["version"], ok["previous_version"]) == (True, 2, 1)
    assert FileChanged.model_validate(room.events[0][1]).actor == "coder"
    data, _ = await room.files.read("src/App.tsx")
    assert b"b = 2" in data


async def test_person_saves_between_read_and_edit_coder_gets_stale() -> None:
    room = app_room()
    tools, _ = room_executor(room)
    read = await tools.execute("read_file", {"path": "src/App.tsx"})
    await room.files.save("src/App.tsx", b"const a = 1;\nconst b = 9;\n", 1, "user-1")  # Dan saves v2
    res = await tools.execute(
        "edit_file", {"path": "src/App.tsx", "base_version": read["version"], "edits": [{"find": "a = 1", "replace": "a = 3"}]}
    )
    assert res["ok"] is False and res["error"].startswith("stale") and res["current_version"] == 2
    data, _ = await room.files.read("src/App.tsx")
    assert data == b"const a = 1;\nconst b = 9;\n"  # Dan's save survives


async def test_coder_write_list_delete() -> None:
    room = app_room()
    tools, _ = room_executor(room)
    assert (await tools.execute("write_file", {"path": "src/App.tsx", "content": "x"}))["error"].startswith("file already exists")
    assert (await tools.execute("write_file", {"path": "src/Nav.tsx", "content": "nav"}))["version"] == 1
    assert (await tools.execute("list_files", {"path": "src"}))["files"] == ["src/App.tsx", "src/Nav.tsx"]
    assert (await tools.execute("delete_file", {"path": "src/Nav.tsx", "base_version": 5}))["error"] == "stale"
    assert (await tools.execute("delete_file", {"path": "src/Nav.tsx", "base_version": 1}))["deleted"] is True
    assert (await tools.execute("read_file", {"path": "../etc/passwd"}))["error"].startswith("path outside")


async def test_build_runs_in_sandbox_on_live_files_and_keeps_snapshot() -> None:
    room = app_room()
    tools, fake = room_executor(room, {wrap("build", BUILD_CMD): [RunResult(0, "", None, 2.0)]})
    out = await tools.execute("run_build", {})
    assert (out["passed"], out["errors"]) == (True, [])
    assert fake.calls[0]["files"] == {"/app/src/App.tsx": b"const a = 1;\nconst b = 1;\n"}
    assert tools.snapshot_uuid == "fake-1"
    await tools.execute("write_file", {"path": "src/Nav.tsx", "content": "nav"})
    assert tools.snapshot_uuid is None  # files changed since the build


async def test_failed_build_reports_errors_and_no_snapshot() -> None:
    room = app_room()
    tools, _ = room_executor(room, {wrap("build", BUILD_CMD): [RunResult(1, "src/App.tsx:1: bad type", None, 1.0)]})
    out = await tools.execute("run_build", {})
    assert (out["passed"], out["errors"], tools.snapshot_uuid) == (False, ["src/App.tsx:1: bad type"], None)


async def test_tests_run_in_sandbox() -> None:
    room = app_room()
    tools, fake = room_executor(room, {wrap("test", TEST_CMD): [RunResult(0, 'MUX_SUMMARY {"passed": 2, "failed": 0}', None, 1.0)]})
    out = await tools.execute("run_tests", {"pattern": "src/App.test.tsx"})
    assert (out["passed"], out["passed_count"]) == (True, 2)
    assert fake.calls[0]["disposable"] is True


# ---- safety ----


async def test_no_runner_and_no_build_root_never_runs_npm(tmp_path: Path) -> None:
    tools = CoderToolExecutor(FileTools(tmp_path))
    assert (await tools.execute("run_build", {}))["errors"] == ["builds are not configured"]
    assert (await tools.execute("run_tests", {}))["errors"] == ["tests are not configured"]


def test_runner_needs_room_files(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        CoderToolExecutor(FileTools(tmp_path), runner=Runner(FakeSandbox({}), app_room().get, image="x"))


async def test_local_tools_use_version_numbers(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("one\n", encoding="utf-8")
    tools = CoderToolExecutor(FileTools(tmp_path))
    assert (await tools.execute("read_file", {"path": "a.ts"}))["version"] == 1
    ok = await tools.execute("edit_file", {"path": "a.ts", "base_version": 1, "edits": [{"find": "one", "replace": "two"}]})
    assert ok["version"] == 2
    (tmp_path / "a.ts").write_text("changed outside\n", encoding="utf-8")
    stale = await tools.execute("edit_file", {"path": "a.ts", "base_version": 2, "edits": [{"find": "x", "replace": "y"}]})
    assert (stale["ok"], stale["current_version"]) == (False, 3)
