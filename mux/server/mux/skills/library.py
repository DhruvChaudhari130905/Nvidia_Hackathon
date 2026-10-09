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
