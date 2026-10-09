# Skills Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The coder can load Claude Code–format skills (`SKILL.md` folders) that each room's owner switches on, listed by name/description and loaded on demand.

**Architecture:** A `mux/skills/` package reads skill folders from `SKILLS_PATH` into a cached `SkillLibrary` and flags skills written for Claude Code's own tools. Rooms record their enabled skills as a room event. The coder's executor gains `use_skill` / `read_skill_file` tools when the room has skills on, its system prompt lists them, the feed shows each use, and compaction keeps the latest skill text. The Tools dialog gets a Skills section.

**Tech Stack:** Python 3.11+ / FastAPI / pydantic, PyYAML (`yaml.safe_load`); Next.js 15 / React / TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-09-skills-engine-design.md`

## Global Constraints

- Backend commands run from `mux/server` with `.venv/bin/python -m pytest`; the full suite is `make test-server` from the repo root.
- Skill names: lowercased, `^[a-z0-9][a-z0-9_-]{0,63}$`; default = folder name. `description` required, cut to 500 characters.
- `SKILL.md` at most 200 KB; at most 100 supporting files per skill, no hidden files, no symlinks.
- At most 30 skills enabled per room; at most 30 listed in the prompt, each description one line ≤ 300 characters.
- `use_skill` / `read_skill_file` return at most 30,000 characters, with a note when cut.
- `read_skill_file` only serves paths that are exactly in the skill's `files` list.
- Skills are off by default in every room; only the owner changes them; everyone in the room sees them.
- Review tasks get the two skill tools (they only read) and still no write tools.

## Review Focus

- **A skill folder with a huge or binary supporting file**: `read_skill_file` returns a readable error, never crashes or floods the context. Test in Task 4.
- **A `SKILL.md` whose frontmatter isn't valid YAML** (Claude Code skills sometimes have colons in descriptions): the skill is skipped with a log line, other skills still load. Test in Task 1.
- **A room that enabled a skill that was later deleted from the server**: the room keeps working, the skill isn't offered, the UI shows it as missing. Test in Task 3.
- **Path tricks in `read_skill_file`** (`../`, absolute paths, a symlink inside the folder): refused. Test in Task 4.
- **The coder calling `use_skill` every turn**: the latest skill text stays in context after compaction, so it doesn't need to. Test in Task 4.

---

## File Structure

| File | Responsibility |
|---|---|
| `mux/server/mux/skills/__init__.py` | package docstring |
| `mux/server/mux/skills/library.py` | `Skill`, `load_skill`, `SkillLibrary`, `library()` |
| `mux/server/mux/skills/compat.py` | `claude_code_issues` |
| `mux/server/mux/config.py`, `pyproject.toml` | `skills_path`; `pyyaml` dependency |
| `mux/server/mux/events/models.py`, `events/wire.py`, `rooms/actor.py` | `room_skills_set` event, `skills_enabled` |
| `mux/server/mux/api/skills.py`, `main.py` | REST API |
| `mux/server/mux/agents/coder/tools/__init__.py`, `tools/skills.py` | `use_skill`, `read_skill_file` |
| `mux/server/mux/agents/coder/compaction.py` | keep latest `use_skill` result |
| `mux/server/mux/rooms/runtime.py` | pass skills, prompt section, `skill.used` |
| `mux/web/src/types/index.ts`, `lib/api.ts`, `lib/reducer.ts`, `components/room/ToolsDialog.tsx` | UI |
| `mux/server/skills/example-clean-code/SKILL.md`, `.env.example`, `docs/03-getting-started.md` | example and docs |

---

### Task 1: Skill library and compatibility check

**Files:**
- Create: `mux/server/mux/skills/__init__.py`, `mux/server/mux/skills/library.py`, `mux/server/mux/skills/compat.py`
- Modify: `mux/server/pyproject.toml` (dependencies), `mux/server/mux/config.py` (after `mcp_allow_private_urls`)
- Test: `mux/server/tests/test_skills_library.py`

**Interfaces:**
- Produces: `Skill(name: str, description: str, body: str, root: Path, files: list[str], issues: list[str], source: str)` with property `compatible -> bool`; `load_skill(folder: Path, source: str) -> Skill | None`; `SkillLibrary(roots: list[tuple[Path, str]])` with `skills() -> dict[str, Skill]` and `reload() -> None`; module function `library() -> SkillLibrary` (tests monkeypatch `mux.skills.library.library`); `claude_code_issues(body: str) -> list[str]`; `settings.skills_path: str = "skills"`.

- [ ] **Step 1: Dependency and setting**

In `mux/server/pyproject.toml` add after `"httpx2",`:

```toml
  # SKILL.md frontmatter (mux.skills)
  "pyyaml",
```

In `mux/server/mux/config.py`, after `mcp_allow_private_urls: bool = False`:

```python

    # Skill folders (each with a SKILL.md) the coder can use when a room switches them on (mux.skills)
    skills_path: str = "skills"
```

- [ ] **Step 2: Write the failing tests**

Create `mux/server/tests/test_skills_library.py`:

```python
"""Reading SKILL.md folders, and spotting skills written for Claude Code's own tools."""

import os
from pathlib import Path

from mux.skills.compat import claude_code_issues
from mux.skills.library import SkillLibrary, load_skill


def write_skill(root: Path, folder: str, text: str, files: dict[str, str] | None = None) -> Path:
    path = root / folder
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(text)
    for name, content in (files or {}).items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(content)
    return path


def test_loads_frontmatter_body_and_files(tmp_path):
    folder = write_skill(tmp_path, "frontend-design", "---\nname: frontend-design\ndescription: Make distinctive UIs\n---\n# Body\nUse bold type.",
                         {"examples/card.html": "<div></div>", ".hidden": "x"})
    skill = load_skill(folder, "server")
    assert skill is not None
    assert (skill.name, skill.description, skill.source) == ("frontend-design", "Make distinctive UIs", "server")
    assert skill.body == "# Body\nUse bold type." and skill.files == ["examples/card.html"] and skill.compatible


def test_name_defaults_to_the_folder_and_bad_skills_are_skipped(tmp_path):
    assert load_skill(write_skill(tmp_path, "Clean-Code", "---\ndescription: Tidy\n---\nbody"), "server").name == "clean-code"  # type: ignore[union-attr]
    assert load_skill(write_skill(tmp_path, "nodesc", "---\nname: nodesc\n---\nbody"), "server") is None
    assert load_skill(write_skill(tmp_path, "badyaml", "---\nname: x\ndescription: a: b: [\n---\nbody"), "server") is None
    assert load_skill(write_skill(tmp_path, "nofront", "just text"), "server") is None
    assert load_skill(write_skill(tmp_path, "bad name!", "---\ndescription: d\n---\nb"), "server") is None
    big = write_skill(tmp_path, "big", "---\ndescription: d\n---\n" + "x" * 210_000)
    assert load_skill(big, "server") is None


def test_symlinks_are_not_supporting_files(tmp_path):
    folder = write_skill(tmp_path, "s", "---\ndescription: d\n---\nb", {"ok.md": "fine"})
    (tmp_path / "outside.txt").write_text("secret")
    os.symlink(tmp_path / "outside.txt", folder / "link.txt")
    assert load_skill(folder, "server").files == ["ok.md"]  # type: ignore[union-attr]


def test_library_first_root_wins_and_reload_picks_up_new_skills(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_skill(a, "tdd", "---\ndescription: from a\n---\nA")
    write_skill(b, "tdd", "---\ndescription: from b\n---\nB")
    lib = SkillLibrary([(a, "server"), (b, "plugin"), (tmp_path / "missing", "server")])
    assert lib.skills()["tdd"].description == "from a"
    write_skill(a, "review", "---\ndescription: r\n---\nR")
    assert "review" not in lib.skills()
    lib.reload()
    assert set(lib.skills()) == {"tdd", "review"}


def test_claude_code_issues():
    assert claude_code_issues("Write the failing test first, then make it pass.") == []
    issues = claude_code_issues("Use TodoWrite for each step. Dispatch a subagent with the Task tool. Run git worktree add.")
    assert issues == ["uses Claude Code sub-agents", "uses Claude Code's task list", "uses git worktrees"]
    assert claude_code_issues("Call EnterPlanMode") == ["uses Claude Code's plan mode"]
    assert claude_code_issues("use the Bash tool") == ["runs shell commands"]
```

- [ ] **Step 3: Run them to verify they fail**

Run: `cd mux/server && .venv/bin/python -m pip install -e '.[dev]' -q && .venv/bin/python -m pytest tests/test_skills_library.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'mux.skills'`

- [ ] **Step 4: Implement**

Create `mux/server/mux/skills/__init__.py`:

```python
"""Skills: SKILL.md guidance packs (Claude Code's format) the coder loads when a room switches them on."""
```

Create `mux/server/mux/skills/compat.py`:

```python
"""Spot skills written for Claude Code's own tools, which MUX's coder doesn't have."""

from __future__ import annotations

_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("TodoWrite", "TaskCreate", "TaskUpdate"), "uses Claude Code's task list"),
    (("Task tool", "Agent tool", "subagent"), "uses Claude Code sub-agents"),
    (("Skill tool", "invoke the Skill"), "loads other skills through Claude Code"),
    (("EnterPlanMode", "ExitPlanMode"), "uses Claude Code's plan mode"),
    (("git worktree",), "uses git worktrees"),
    (("Bash tool", "Bash("), "runs shell commands"),
]


def claude_code_issues(body: str) -> list[str]:
    """Reasons this skill needs Claude Code (sorted, each once); empty when MUX's coder can follow it."""
    return sorted({reason for needles, reason in _PATTERNS if any(needle in body for needle in needles)})
```

Create `mux/server/mux/skills/library.py`:

```python
"""Skill folders on the server: SKILL.md (YAML frontmatter + instructions) plus supporting files."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Optional

import yaml

from mux.config import settings
from mux.skills.compat import claude_code_issues

logger = logging.getLogger(__name__)

MAX_SKILL_BYTES = 200_000
MAX_FILES = 100
MAX_DESCRIPTION = 500
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    root: Path
    files: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    source: str = "server"

    @property
    def compatible(self) -> bool:
        return not self.issues


def _supporting_files(folder: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if any(part.startswith(".") for part in relative.parts) or path.is_symlink() or not path.is_file():
            continue
        if any(parent.is_symlink() for parent in path.parents if folder in parent.parents):
            continue
        if relative.as_posix() == "SKILL.md":
            continue
        files.append(relative.as_posix())
        if len(files) >= MAX_FILES:
            break
    return files


def load_skill(folder: Path, source: str) -> Optional[Skill]:
    """The skill in `folder`, or None (logged) when it can't be used."""
    path = folder / "SKILL.md"
    try:
        if path.stat().st_size > MAX_SKILL_BYTES:
            logger.warning(f"Skipping skill {folder.name}: SKILL.md is over {MAX_SKILL_BYTES} bytes")
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Skipping skill {folder.name}: {e}")
        return None
    match = _FRONTMATTER.match(text)
    if not match:
        logger.warning(f"Skipping skill {folder.name}: SKILL.md has no --- frontmatter ---")
        return None
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        logger.warning(f"Skipping skill {folder.name}: frontmatter isn't valid YAML ({e})")
        return None
    if not isinstance(meta, dict):
        logger.warning(f"Skipping skill {folder.name}: frontmatter isn't a mapping")
        return None
    name = str(meta.get("name") or folder.name).strip().lower()
    description = " ".join(str(meta.get("description") or "").split())[:MAX_DESCRIPTION]
    if not _NAME.fullmatch(name):
        logger.warning(f"Skipping skill {folder.name}: name {name!r} isn't allowed")
        return None
    if not description:
        logger.warning(f"Skipping skill {folder.name}: no description")
        return None
    body = match.group(2).strip()
    return Skill(name, description, body, folder, _supporting_files(folder), claude_code_issues(body), source)


class SkillLibrary:
    """Every skill under the given roots; the first root wins when two skills share a name."""

    def __init__(self, roots: list[tuple[Path, str]]) -> None:
        self.roots = roots
        self._skills: Optional[dict[str, Skill]] = None

    def skills(self) -> dict[str, Skill]:
        if self._skills is None:
            self.reload()
        assert self._skills is not None
        return self._skills

    def reload(self) -> None:
        found: dict[str, Skill] = {}
        for root, source in self.roots:
            if not root.is_dir():
                continue
            for folder in sorted(p for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()):
                skill = load_skill(folder, source)
                if skill is None:
                    continue
                if skill.name in found:
                    logger.warning(f"Skill {skill.name} in {folder} ignored: {found[skill.name].root} has the same name")
                    continue
                found[skill.name] = skill
        self._skills = found


@cache
def library() -> SkillLibrary:
    """The server's skills (SKILLS_PATH). Part 2 adds installed plugins' skill folders as more roots."""
    return SkillLibrary([(Path(settings.skills_path), "server")])
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_skills_library.py -q`
Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add mux/server/pyproject.toml mux/server/mux/config.py mux/server/mux/skills mux/server/tests/test_skills_library.py
git commit -m "Read SKILL.md skill folders and flag ones that need Claude Code"
```

---

### Task 2: Room event for enabled skills

**Files:**
- Modify: `mux/server/mux/events/models.py` (EventType after `ROOM_AI_SETTINGS_CLEARED`; class after `RoomAiSettingsClearedEvent`; `Event` union; `__all__`)
- Modify: `mux/server/mux/events/wire.py` (import; branch before `# Invites (room_invite_*) aren't sent`)
- Modify: `mux/server/mux/rooms/actor.py` (import; `__init__` after `self.ai_settings`; method after `clear_ai_settings`; replay after the AI branches)
- Modify: `mux/web/src/types/index.ts` (event union: `'skills.changed'`, `'skill.used'`)
- Test: `mux/server/tests/test_skills_room.py`

**Interfaces:**
- Produces: `RoomSkillsSetEvent(enabled: list[str])`; `actor.skills_enabled: set[str]`; `async actor.set_skills(enabled: list[str], user_id: str) -> None`; wire type `skills.changed` `{enabled}`.

- [ ] **Step 1: Write the failing test**

Create `mux/server/tests/test_skills_room.py`:

```python
"""A room's enabled skills are a room event."""

import json

import pytest

import mux.rooms.registry as room_registry
from mux.events.log import InMemoryEventLog
from mux.events.wire import to_envelope
from mux.rooms.registry import RoomRegistry


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logs: dict[str, InMemoryEventLog] = {}
    monkeypatch.setattr(room_registry, "get_event_log", lambda rid: logs.setdefault(rid, InMemoryEventLog(rid)))
    return RoomRegistry(), logs


async def test_enabled_skills_replay(registry):
    reg, logs = registry
    actor = await reg.create_room("room_sk1", "alice", name="Docs")
    assert actor.skills_enabled == set()
    await actor.set_skills(["tdd", "frontend-design"], "alice")
    wire = json.dumps([to_envelope(e) for e in logs["room_sk1"]._events])
    assert '"enabled": ["frontend-design", "tdd"]' in wire
    await reg.stop_room("room_sk1")
    again = await reg.get_room_or_rehydrate("room_sk1")
    assert again is not None and again.skills_enabled == {"tdd", "frontend-design"}
    await reg.shutdown_all()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_skills_room.py -q`
Expected: FAIL with `AttributeError: 'RoomActor' object has no attribute 'skills_enabled'`

- [ ] **Step 3: Implement**

`mux/server/mux/events/models.py` — in `EventType` after `ROOM_AI_SETTINGS_CLEARED = "room_ai_settings_cleared"`:

```python
    ROOM_SKILLS_SET = "room_skills_set"
```

after the `RoomAiSettingsClearedEvent` class:

```python


class RoomSkillsSetEvent(BaseEvent):
    """The owner chose which skills (mux/skills) the room's coder may use."""
    type: EventType = EventType.ROOM_SKILLS_SET
    enabled: List[str] = Field(default_factory=list, description="Skill names, sorted")
```

Add `RoomSkillsSetEvent,` to the `Event` union after `RoomAiSettingsClearedEvent,` and `"RoomSkillsSetEvent",` to `__all__` after `"RoomAiSettingsClearedEvent",`.

`mux/server/mux/events/wire.py` — add `RoomSkillsSetEvent,` to the models import (alphabetical), and before `# Invites (room_invite_*) aren't sent`:

```python
    if t == EventType.ROOM_SKILLS_SET:
        return "skills.changed", {"enabled": cast(RoomSkillsSetEvent, event).enabled}
```

`mux/server/mux/rooms/actor.py` — add `RoomSkillsSetEvent,` to the models import after `RoomAiSettingsClearedEvent,`; in `__init__` after `self.ai_settings: Optional[dict[str, Any]] = None`:

```python
        self.skills_enabled: set[str] = set()  # skills (mux/skills) the room's coder may use
```

after `clear_ai_settings`:

```python

    async def set_skills(self, enabled: list[str], user_id: str) -> None:
        async with self._lock:
            names = sorted(set(enabled))
            self.skills_enabled = set(names)
            await self._emit(RoomSkillsSetEvent(**self._event_fields(user_id), enabled=names))
```

in the replay method after the `ROOM_AI_SETTINGS_CLEARED` branch:

```python
            elif t == EventType.ROOM_SKILLS_SET:
                self.skills_enabled = set(cast(RoomSkillsSetEvent, event).enabled)
```

`mux/web/src/types/index.ts` — after `| 'ai.error'` add:

```ts
  | 'skills.changed'
  | 'skill.used'
```

- [ ] **Step 4: Run the tests**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_skills_room.py tests/test_api.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add mux/server/mux/events/models.py mux/server/mux/events/wire.py mux/server/mux/rooms/actor.py mux/server/tests/test_skills_room.py mux/web/src/types/index.ts
git commit -m "Keep each room's enabled skills as a room event"
```

---

### Task 3: Skills API

**Files:**
- Create: `mux/server/mux/api/skills.py`
- Modify: `mux/server/mux/main.py` (import list; mount after the AI router)
- Test: `mux/server/tests/test_api.py` (append)

**Interfaces:**
- Consumes: `mux.skills.library.library()` (call through the module: `skills_library.library()`), `Skill` (T1); `actor.skills_enabled`, `actor.set_skills` (T2).
- Produces: `GET /rooms/{id}/skills` → `[{name, description, source, compatible, issues, enabled, files, missing}]` (`files` is a count; `missing: true` rows are enabled names no longer on the server); `PUT /rooms/{id}/skills` `{enabled: [...]}`; `POST /rooms/{id}/skills/reload`. `MAX_ENABLED_SKILLS = 30`.

- [ ] **Step 1: Write the failing tests**

Append to `mux/server/tests/test_api.py`:

```python


# --- Skills ------------------------------------------------------------------

@pytest.fixture
def skills_dir(tmp_path, monkeypatch):
    import mux.skills.library as skills_library
    root = tmp_path / "skills"

    def add(folder: str, description: str, body: str = "Do it well.") -> None:
        (root / folder).mkdir(parents=True)
        (root / folder / "SKILL.md").write_text(f"---\nname: {folder}\ndescription: {description}\n---\n{body}")

    add("frontend-design", "Distinctive UIs")
    add("subagent-dev", "Delegate", "Dispatch a subagent with the Task tool.")
    lib = skills_library.SkillLibrary([(root, "server")])
    monkeypatch.setattr(skills_library, "library", lambda: lib)
    return add


def test_owner_switches_skills_on(client, skills_dir):
    rid = create_room(client)
    listed = client.get(f"/rooms/{rid}/skills", headers=auth("alice")).json()
    assert [s["name"] for s in listed] == ["frontend-design", "subagent-dev"] and not any(s["enabled"] for s in listed)
    assert listed[1]["compatible"] is False and listed[1]["issues"] == ["uses Claude Code sub-agents"]
    r = client.put(f"/rooms/{rid}/skills", json={"enabled": ["frontend-design"]}, headers=auth("alice"))
    assert r.status_code == 200 and [s["name"] for s in r.json() if s["enabled"]] == ["frontend-design"]
    client.post(f"/rooms/{rid}/members", json={"user_id": "bob", "role": "viewer"}, headers=auth("alice"))
    assert client.get(f"/rooms/{rid}/skills", headers=auth("bob")).status_code == 200
    assert client.put(f"/rooms/{rid}/skills", json={"enabled": []}, headers=auth("bob")).status_code == 403
    assert client.put(f"/rooms/{rid}/skills", json={"enabled": ["nope"]}, headers=auth("alice")).status_code == 400


def test_skills_reload_and_removed_skills_show_as_missing(client, skills_dir, tmp_path):
    import shutil
    rid = create_room(client)
    client.put(f"/rooms/{rid}/skills", json={"enabled": ["frontend-design"]}, headers=auth("alice"))
    skills_dir("tdd", "Tests first")
    shutil.rmtree(tmp_path / "skills" / "frontend-design")
    listed = client.post(f"/rooms/{rid}/skills/reload", headers=auth("alice")).json()
    by_name = {s["name"]: s for s in listed}
    assert "tdd" in by_name and by_name["frontend-design"]["missing"] is True and by_name["frontend-design"]["enabled"] is True
    registry_call(client, room_registry.get_registry().stop_room, rid)
    assert any(s["enabled"] for s in client.get(f"/rooms/{rid}/skills", headers=auth("alice")).json())


def test_skill_limit(client, skills_dir):
    for i in range(30):
        skills_dir(f"s{i}", "x")
    rid = create_room(client)
    client.post(f"/rooms/{rid}/skills/reload", headers=auth("alice"))
    names = [f"s{i}" for i in range(30)] + ["frontend-design"]
    assert client.put(f"/rooms/{rid}/skills", json={"enabled": names}, headers=auth("alice")).status_code == 400
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_api.py -q -k skill`
Expected: FAIL (404 on `/rooms/{id}/skills`)

- [ ] **Step 3: Implement**

Create `mux/server/mux/api/skills.py`:

```python
"""Which skills (mux/skills) a room's coder may use: everyone in the room sees them, the owner chooses."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import mux.skills.library as skills_library
from mux.api.deps import User, get_room_actor_dep, require_owner, require_viewer
from mux.rooms.actor import RoomActor

router = APIRouter()

MAX_ENABLED_SKILLS = 30


class SkillsRequest(BaseModel):
    enabled: list[str] = Field(default_factory=list, max_length=200)


def skills_view(actor: RoomActor) -> list[dict[str, Any]]:
    available = skills_library.library().skills()
    rows = [{
        "name": s.name, "description": s.description, "source": s.source, "compatible": s.compatible,
        "issues": s.issues, "enabled": s.name in actor.skills_enabled, "files": len(s.files), "missing": False,
    } for s in available.values()]
    rows += [{"name": name, "description": "", "source": "", "compatible": True, "issues": [], "enabled": True,
              "files": 0, "missing": True} for name in actor.skills_enabled if name not in available]
    return sorted(rows, key=lambda row: row["name"])


@router.get("/{room_id}/skills")
async def get_skills(room_id: str, current_user: User = Depends(require_viewer),
                     actor: RoomActor = Depends(get_room_actor_dep)) -> list[dict[str, Any]]:
    return skills_view(actor)


@router.put("/{room_id}/skills")
async def set_skills(room_id: str, request: SkillsRequest, current_user: User = Depends(require_owner),
                     actor: RoomActor = Depends(get_room_actor_dep)) -> list[dict[str, Any]]:
    wanted = set(request.enabled)
    known = set(skills_library.library().skills()) | actor.skills_enabled  # missing ones may stay switched on
    unknown = sorted(wanted - known)
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No skill named {', '.join(unknown)}")
    if len(wanted) > MAX_ENABLED_SKILLS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"A room can have at most {MAX_ENABLED_SKILLS} skills on")
    await actor.set_skills(sorted(wanted), current_user.id)
    return skills_view(actor)


@router.post("/{room_id}/skills/reload")
async def reload_skills(room_id: str, current_user: User = Depends(require_owner),
                        actor: RoomActor = Depends(get_room_actor_dep)) -> list[dict[str, Any]]:
    skills_library.library().reload()
    return skills_view(actor)
```

In `mux/server/mux/main.py`, change the import to `from mux.api import rooms, files, commands, export, ws, mcp, ai, skills` and after the AI `include_router` add:

```python
    app.include_router(skills.router, prefix="/rooms", tags=["skills"])
```

- [ ] **Step 4: Run the tests**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_api.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add mux/server/mux/api/skills.py mux/server/mux/main.py mux/server/tests/test_api.py
git commit -m "Add the room skills API"
```

---

### Task 4: Coder skill tools, prompt, feed and compaction

**Files:**
- Create: `mux/server/mux/agents/coder/tools/skills.py`
- Modify: `mux/server/mux/agents/coder/tools/__init__.py` (imports; `READ_ONLY_TOOLS`; `__init__` param `skills`; `execute` handlers; `schemas`)
- Modify: `mux/server/mux/agents/coder/compaction.py` (`_reads_to_keep`)
- Modify: `mux/server/mux/rooms/runtime.py` (imports; `_run`; `_context`; `_Narrated.execute`; `_summary`)
- Test: `mux/server/tests/test_tools.py`, `mux/server/tests/test_runtime.py` (append)

**Interfaces:**
- Consumes: `Skill`, `skills_library.library()` (T1); `actor.skills_enabled`, `set_skills` (T2).
- Produces: `SKILL_TOOL_SCHEMAS: list[dict]`; `use_skill(skills: dict[str, Skill], name: str) -> dict`; `read_skill_file(skills: dict[str, Skill], name: str, path: str) -> dict`; `skills_prompt(skills: dict[str, Skill]) -> str`; `MAX_SKILL_CHARS = 30_000`; `CoderToolExecutor(..., skills: dict[str, Skill] | None = None)`; feed notice `skill.used` `{name}`.

- [ ] **Step 1: Write the failing tests**

Append to `mux/server/tests/test_tools.py`:

```python


# skills

def _skill(tmp_path: Path, files: dict[str, str] | None = None):
    from mux.skills.library import load_skill
    folder = tmp_path / "skills" / "frontend-design"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\ndescription: Distinctive UIs\n---\nUse bold type and real contrast.")
    for name, content in (files or {}).items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(content)
    skill = load_skill(folder, "server")
    assert skill is not None
    return skill


async def test_skill_tools_are_offered_only_with_skills(tmp_path):
    names = lambda tools: {s["function"]["name"] for s in tools.schemas()}
    assert "use_skill" not in names(CoderToolExecutor(FileTools(tmp_path)))
    skill = _skill(tmp_path)
    with_skills = CoderToolExecutor(FileTools(tmp_path), skills={"frontend-design": skill})
    assert {"use_skill", "read_skill_file"} <= names(with_skills)
    review = CoderToolExecutor(FileTools(tmp_path), skills={"frontend-design": skill}, read_only=True)
    assert names(review) == {"read_file", "list_files", "web_search", "finish_task", "use_skill", "read_skill_file"}


async def test_use_skill_and_read_skill_file(tmp_path):
    skill = _skill(tmp_path, {"examples/card.html": "<div class='card'></div>", "big.txt": "y" * 40_000})
    (tmp_path / "secret.txt").write_text("nope")
    tools = CoderToolExecutor(FileTools(tmp_path), skills={"frontend-design": skill})
    used = await tools.execute("use_skill", {"name": "frontend-design"})
    assert used == {"ok": True, "name": "frontend-design", "instructions": "Use bold type and real contrast.",
                    "files": ["big.txt", "examples/card.html"]}
    assert (await tools.execute("use_skill", {"name": "other"}))["ok"] is False
    card = await tools.execute("read_skill_file", {"name": "frontend-design", "path": "examples/card.html"})
    assert card == {"ok": True, "path": "examples/card.html", "content": "<div class='card'></div>"}
    big = await tools.execute("read_skill_file", {"name": "frontend-design", "path": "big.txt"})
    assert big["ok"] and len(big["content"]) < 31_000 and "cut" in big["content"]
    for path in ("../../secret.txt", "/etc/passwd", "SKILL.md", "examples/../examples/card.html"):
        assert (await tools.execute("read_skill_file", {"name": "frontend-design", "path": path}))["ok"] is False


async def test_binary_skill_files_are_refused(tmp_path):
    skill = _skill(tmp_path)
    (skill.root / "logo.png").write_bytes(b"\x89PNG\x00\xff\xfe")
    from mux.skills.library import load_skill
    skill = load_skill(skill.root, "server")
    tools = CoderToolExecutor(FileTools(tmp_path), skills={"frontend-design": skill})  # type: ignore[dict-item]
    result = await tools.execute("read_skill_file", {"name": "frontend-design", "path": "logo.png"})
    assert result["ok"] is False and "text" in result["error"]


def test_compaction_keeps_the_latest_skill_text():
    def call(cid: str, name: str, args: dict, result: str) -> list[dict]:
        return [{"role": "assistant", "content": "", "tool_calls": [
                    {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]},
                {"role": "tool", "tool_call_id": cid, "content": result}]
    body = json.dumps({"ok": True, "name": "frontend-design", "instructions": "I" * 500, "files": []})
    messages = [*call("s1", "use_skill", {"name": "frontend-design"}, body),
                *call("r1", "list_files", {"path": "."}, "x" * 500),
                {"role": "assistant", "content": "", "tool_calls": []}]
    out = compact(messages)
    assert out[1]["content"] == body and out[3]["content"].startswith("[previous tool result]")
```

Append to `mux/server/tests/test_runtime.py`:

```python


# --- skills ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_coder_sees_and_uses_the_rooms_skills(setup, tmp_path, monkeypatch):
    import mux.skills.library as skills_library
    root = tmp_path / "skill-root"
    for name, desc in (("frontend-design", "Distinctive UIs"), ("tdd", "Tests first")):
        (root / name).mkdir(parents=True)
        (root / name / "SKILL.md").write_text(f"---\ndescription: {desc}\n---\nInstructions for {name}.")
    lib = skills_library.SkillLibrary([(root, "server")])
    monkeypatch.setattr(skills_library, "library", lambda: lib)

    registry, llm, logs, _ = setup
    actor = await new_room(registry, llm, logs)
    log = logs[actor.room_id]
    await actor.set_skills(["frontend-design", "gone"], "alice")  # "gone" isn't on the server
    llm.push(tool_reply(("use_skill", {"name": "frontend-design"})), tool_reply(("finish_task", {"summary": "done"})))
    await actor.approve_plan_items(["t1"], "alice")
    await until(lambda: of_type(log, EventType.CHECKPOINT_CREATED))

    coder_call = next(c for c in llm.calls if c.tools)
    system = coder_call.messages[0]["content"]
    assert "- frontend-design: Distinctive UIs" in system and "tdd" not in system and "gone" not in system
    assert notices(log, "skill.used") == [{"name": "frontend-design"}]
    await registry.shutdown_all()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_tools.py tests/test_runtime.py -q -k "skill"`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'skills'`)

- [ ] **Step 3: The skill tools**

Create `mux/server/mux/agents/coder/tools/skills.py`:

```python
"""use_skill / read_skill_file: the coder loads a room's skill instructions (mux/skills) when it needs them."""

from __future__ import annotations

from typing import Any

from mux.skills.library import Skill

MAX_SKILL_CHARS = 30_000
MAX_PROMPT_SKILLS = 30

SKILL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "use_skill",
            "description": "Load a skill's instructions (and the list of its supporting files) before following it.",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill_file",
            "description": "Read one of a skill's supporting files, by a path use_skill listed.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "path": {"type": "string"}},
                "required": ["name", "path"],
            },
        },
    },
]


def _cut(text: str) -> str:
    if len(text) <= MAX_SKILL_CHARS:
        return text
    return text[:MAX_SKILL_CHARS] + f"\n[cut: {len(text) - MAX_SKILL_CHARS} more characters]"


def use_skill(skills: dict[str, Skill], name: str) -> dict[str, Any]:
    skill = skills.get(str(name).strip().lower())
    if skill is None:
        return {"ok": False, "error": f"No skill named {name} is switched on in this room"}
    return {"ok": True, "name": skill.name, "instructions": _cut(skill.body), "files": skill.files}


def read_skill_file(skills: dict[str, Skill], name: str, path: str) -> dict[str, Any]:
    skill = skills.get(str(name).strip().lower())
    if skill is None:
        return {"ok": False, "error": f"No skill named {name} is switched on in this room"}
    if path not in skill.files:  # exact match against the listed files: no way out of the skill's folder
        return {"ok": False, "error": f"{path} isn't one of {skill.name}'s files; use a path use_skill listed"}
    try:
        raw = (skill.root / path).read_bytes()
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"ok": False, "error": f"{path} isn't a text file"}
    except OSError as e:
        return {"ok": False, "error": f"Can't read {path}: {e}"}
    if "\x00" in text:
        return {"ok": False, "error": f"{path} isn't a text file"}
    return {"ok": True, "path": path, "content": _cut(text)}


def skills_prompt(skills: dict[str, Skill]) -> str:
    """The system prompt section listing the room's skills, or "" when there are none."""
    if not skills:
        return ""
    lines = [f"- {s.name}: {s.description[:300]}" for s in sorted(skills.values(), key=lambda s: s.name)[:MAX_PROMPT_SKILLS]]
    return ("Skills you can use (call use_skill with the name before following one; only when the task needs it):\n"
            + "\n".join(lines))
```

- [ ] **Step 4: Wire them into the executor**

In `mux/server/mux/agents/coder/tools/__init__.py`:

- Add after `from .search import web_search`:

```python
from .skills import SKILL_TOOL_SCHEMAS, read_skill_file, use_skill
```

and after `from mux.sandbox.runner import Runner`:

```python
from mux.skills.library import Skill
```

- Change `READ_ONLY_TOOLS = {"read_file", "list_files", "web_search", "finish_task"}` to:

```python
READ_ONLY_TOOLS = {"read_file", "list_files", "web_search", "finish_task", "use_skill", "read_skill_file"}
```

- In `__init__`, add the parameter `skills: dict[str, Skill] | None = None,` after `read_only: bool = False,` and in the body after `self.read_only = read_only ...`:

```python
        self.skills = skills or {}  # the room's enabled skills (mux/skills); tools offered only when non-empty
```

- In `execute`'s `handlers` dict add:

```python
            "use_skill": lambda name: use_skill(self.skills, name),
            "read_skill_file": lambda name, path: read_skill_file(self.skills, name, path),
```

- Replace `schemas` with:

```python
    def schemas(self) -> list[dict[str, Any]]:
        """The tool schemas to offer the model: build tools only when builds can run, skill tools only with skills."""
        schemas = TOOL_SCHEMAS + (SKILL_TOOL_SCHEMAS if self.skills else [])
        if self.read_only:
            return [s for s in schemas if s["function"]["name"] in READ_ONLY_TOOLS]
        if self.can_build:
            return schemas
        return [s for s in schemas if s["function"]["name"] not in ("run_build", "run_tests")]
```

- [ ] **Step 5: Compaction keeps the latest skill text**

In `mux/server/mux/agents/coder/compaction.py`, in `_reads_to_keep` replace:

```python
        name, arguments = calls.get(str(message.get("tool_call_id", "")), ("", {}))
        path = arguments.get("path")
        if not path:
            continue
        if name in _CHANGES and _succeeded(message.get("content")):
```

with:

```python
        name, arguments = calls.get(str(message.get("tool_call_id", "")), ("", {}))
        if name == "use_skill" and arguments.get("name"):
            key = ("skill", arguments["name"])
            size = len(str(message.get("content", "")))
            if key not in seen and used + size <= KEPT_READS_BUDGET:
                kept.add(i)
                used += size
            seen.add(key)
            continue
        path = arguments.get("path")
        if not path:
            continue
        if name in _CHANGES and _succeeded(message.get("content")):
```

- [ ] **Step 6: Runtime: pass skills, list them, narrate**

In `mux/server/mux/rooms/runtime.py`:

- Add imports after `from mux.mcp.toolset import ALLOW, DENY, McpToolset`:

```python
import mux.skills.library as skills_library
from mux.agents.coder.tools.skills import skills_prompt
```

- In `_run`, replace:

```python
        review = item.get("kind") == "review"
        executor = CoderToolExecutor(ActorFileTools(self.actor), search=self.search, on_question=on_question,
                                     read_only=review)
```

with:

```python
        review = item.get("kind") == "review"
        skills = self._skills()
        executor = CoderToolExecutor(ActorFileTools(self.actor), search=self.search, on_question=on_question,
                                     read_only=review, skills=skills)
```

and change `await self._context(item, executor.can_build, review=review)` to `await self._context(item, executor.can_build, review=review, skills=skills)`.

- Add the method before `_context`:

```python
    def _skills(self) -> dict[str, Any]:
        """The room's enabled skills that exist on the server (a removed one is simply not offered)."""
        available = skills_library.library().skills()
        return {name: available[name] for name in sorted(self.actor.skills_enabled) if name in available}
```

- Change `_context`'s signature to `async def _context(self, item: dict[str, Any], can_build: bool, *, review: bool = False, skills: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:` and its `system_prompt=` line to:

```python
            system_prompt="\n\n".join(p for p in (REVIEW_SYSTEM_PROMPT if review else coder_system_prompt(can_build),
                                                  skills_prompt(skills or {})) if p),
```

- In `_Narrated.execute`, after `result = await self.inner.execute(name, arguments)`:

```python
        if name == "use_skill" and isinstance(result, dict) and result.get("ok"):
            await self.actor.post_notice("skill.used", {"name": result.get("name")}, CODER)
```

- In `_summary`, before `if "content" in result:  # MCP tool output`:

```python
    if "instructions" in result:  # use_skill: the skill's text is long; the name is enough for the feed
        return f"skill {result.get('name')}"
```

- [ ] **Step 7: Run the tests**

Run: `cd mux/server && .venv/bin/python -m pytest tests/test_tools.py tests/test_runtime.py -q && .venv/bin/python -m pytest -q && .venv/bin/pyright mux tests scripts`
Expected: all pass; pyright `0 errors`.

- [ ] **Step 8: Commit**

```bash
git add mux/server/mux/agents/coder/tools mux/server/mux/agents/coder/compaction.py mux/server/mux/rooms/runtime.py mux/server/tests/test_tools.py mux/server/tests/test_runtime.py
git commit -m "Let the coder load the room's skills with use_skill"
```

---

### Task 5: Web: Skills section and feed line

**Files:**
- Modify: `mux/web/src/types/index.ts` (after `RoomAi`), `mux/web/src/lib/api.ts` (imports; `demoFetch`; methods after `clearAi`), `mux/web/src/lib/reducer.ts` (before `case 'ai.changed':`), `mux/web/src/components/room/ToolsDialog.tsx`

**Interfaces:**
- Consumes: T3 API shape.
- Produces: `RoomSkill` type; `api.getSkills`, `api.setSkills`, `api.reloadSkills`.

- [ ] **Step 1: Types and API**

`mux/web/src/types/index.ts` after the `RoomAi` interface:

```ts
// A skill (SKILL.md guidance pack) the room's coder may use; the owner switches them on
export interface RoomSkill {
  name: string;
  description: string;
  source: string;
  compatible: boolean;
  issues: string[];
  enabled: boolean;
  files: number;
  missing: boolean;
}
```

`mux/web/src/lib/api.ts`: add `RoomSkill` to the `@/types` import; in `demoFetch` before the `/ai` line:

```ts
  if (roomMatch && roomMatch[2]?.startsWith('/skills')) return [] as T;
```

after `clearAi`:

```ts

  // Skills the room's coder may use: anyone reads, the owner switches them on
  getSkills: (id: string) => fetchWithAuth<RoomSkill[]>(`/rooms/${id}/skills`),
  setSkills: (id: string, enabled: string[]) =>
    fetchWithAuth<RoomSkill[]>(`/rooms/${id}/skills`, { method: 'PUT', body: JSON.stringify({ enabled }) }),
  reloadSkills: (id: string) => fetchWithAuth<RoomSkill[]>(`/rooms/${id}/skills/reload`, { method: 'POST' }),
```

- [ ] **Step 2: Feed line**

`mux/web/src/lib/reducer.ts`, before `case 'ai.changed':`:

```ts
    case 'skill.used': {
      const { name } = (event as unknown as { payload: { name: string } }).payload;
      newState.messages = [...newState.messages, {
        id: `skill-${event.seq}`,
        room_id: newState.room.id,
        user_id: 'coder',
        text: `Using skill: ${name}`,
        created_at: event.ts,
        user: { id: 'coder', email: '', name: 'Coder', initials: 'CD', color: 'hsl(140, 60%, 55%)' },
      } as Message];
      break;
    }
    case 'skills.changed':
      // The Tools dialog loads skills when it opens
      break;
```

- [ ] **Step 3: Skills section in the Tools dialog**

In `mux/web/src/components/room/ToolsDialog.tsx`:

- Change the type import to `import type { McpTool, McpToolSetting, RoomMcp, RoomSkill } from '@/types';`.
- After `const [mcp, setMcp] = useState<RoomMcp | null>(null);` add `const [skills, setSkills] = useState<RoomSkill[] | null>(null);`.
- In the `useEffect`, after the `api.getMcp(...)` line add:

```tsx
    api.getSkills(roomId).then(setSkills).catch(e => setError(e instanceof Error ? e.message : 'Could not load skills'));
```

- After the `run` function add:

```tsx
  const runSkills = async (action: () => Promise<RoomSkill[]>) => {
    setBusy(true);
    setError(null);
    try {
      setSkills(await action());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong');
    } finally {
      setBusy(false);
    }
  };

  const toggleSkill = (name: string, on: boolean) => {
    const enabled = (skills ?? []).filter(s => s.enabled && s.name !== name).map(s => s.name);
    return runSkills(() => api.setSkills(roomId, on ? [...enabled, name] : enabled));
  };
```

- Right after the `{error && ...}` line, add the section:

```tsx
        {skills && (
          <div className={section}>
            <div className="flex items-center justify-between gap-2">
              <p className="font-medium">Skills</p>
              {isOwner && (
                <button type="button" className="btn p-1" disabled={busy} title="Re-read the server's skills folder" aria-label="Reload skills"
                  onClick={() => runSkills(() => api.reloadSkills(roomId))}><RefreshCw className="w-3.5 h-3.5" /></button>
              )}
            </div>
            {skills.length === 0 && <p className="text-sm text-[var(--muted)]">No skills on the server yet. Put skill folders (each with a SKILL.md) in the server&apos;s skills folder.</p>}
            {skills.map(skill => (
              <label key={skill.name} className="flex items-start gap-2 text-sm" title={skill.description}>
                <input type="checkbox" className="mt-1" checked={skill.enabled} disabled={!isOwner || busy}
                  onChange={e => toggleSkill(skill.name, e.target.checked)} />
                <span className="min-w-0">
                  <span className="font-mono">{skill.name}</span>
                  {skill.missing && <span className="ml-2 text-xs text-[var(--conflict)]">missing on the server</span>}
                  {!skill.compatible && (
                    <span className="ml-2 text-xs text-[var(--conflict)]" title={skill.issues.join('; ')}>needs Claude Code</span>
                  )}
                  {skill.description && <span className="block truncate text-xs text-[var(--muted)]">{skill.description}</span>}
                </span>
              </label>
            ))}
          </div>
        )}
```

- Change the dialog title text from `MCP tools` to `Tools and skills`.

- [ ] **Step 4: Type-check, lint, build**

Run: `cd mux/web && npx tsc --noEmit && npm run lint -- --max-warnings=0 && NEXT_DIST_DIR=.next-build npm run build`
Expected: no errors; `✓ Compiled successfully`.

- [ ] **Step 5: Commit**

```bash
git add mux/web/src/types/index.ts mux/web/src/lib/api.ts mux/web/src/lib/reducer.ts mux/web/src/components/room/ToolsDialog.tsx
git commit -m "Add skills to the room's Tools dialog and feed"
```

---

### Task 6: Example skill and docs

**Files:**
- Create: `mux/server/skills/example-clean-code/SKILL.md`
- Modify: `mux/server/.env.example`, `docs/03-getting-started.md`

- [ ] **Step 1: Example skill**

Create `mux/server/skills/example-clean-code/SKILL.md`:

```markdown
---
name: example-clean-code
description: Keep changes small and readable - clear names, short functions, no dead code. Use for any code change.
---

# Clean code

When you change code:

1. Name things for what they mean in the app ("cartTotal", not "x2").
2. Keep functions short; split one that does two jobs.
3. Delete code you replace. No commented-out blocks, no unused imports.
4. Match the file's existing style: quotes, indentation, naming.
5. Handle the failure a user can actually hit (empty list, network error) with a clear message.
```

- [ ] **Step 2: Settings and docs**

In `mux/server/.env.example`, after `MCP_CONFIG_PATH=mcp.json`:

```
# Skill folders (each with a SKILL.md, Claude Code's format) rooms can switch on, relative to mux/server.
SKILLS_PATH=skills
```

In `docs/03-getting-started.md`, after the "A room's own AI model" section add:

```markdown
## 🧩 Skills

Skills are guidance packs in Claude Code's format: a folder with a `SKILL.md` (a `name` and `description` header, then instructions) and any supporting files. Put skill folders in `mux/server/skills/` (or wherever `SKILLS_PATH` points). Skills you already have in Claude Code live under `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/`; copy a skill's folder across. Check each skill's license first.

In a room, the owner opens **Tools** and switches skills on (they're off by default); **Reload** picks up folders added since the server started. The coder sees each enabled skill's name and description and loads the full instructions with `use_skill` when a task needs it; the feed shows "Using skill: …".

Skills written for Claude Code's own tools (task lists, sub-agents, plan mode, git worktrees, the Bash tool) are marked **needs Claude Code**: MUX's coder can't do those parts. Guidance skills (design, testing practice, code review) work fully.
```

- [ ] **Step 3: Final verification and commit**

Run: `make test-server` (from the repo root) and `cd mux/web && npx tsc --noEmit && npm run lint -- --max-warnings=0`
Expected: all pass, no errors.

```bash
git add mux/server/skills mux/server/.env.example docs/03-getting-started.md
git commit -m "Add an example skill and document skills"
```
