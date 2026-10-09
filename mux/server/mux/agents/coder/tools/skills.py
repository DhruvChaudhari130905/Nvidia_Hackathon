"""use_skill / read_skill_file: the coder loads a room's skill instructions (mux/skills) when it needs them."""

from __future__ import annotations

from typing import Any

from mux.skills.library import Skill

MAX_SKILL_CHARS = 30_000
MAX_SKILL_FILE_BYTES = 1_000_000  # bigger supporting files (datasets, assets) aren't read at all
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
        if (skill.root / path).stat().st_size > MAX_SKILL_FILE_BYTES:
            return {"ok": False, "error": f"{path} is too large to read (over {MAX_SKILL_FILE_BYTES // 1_000_000} MB)"}
        text = (skill.root / path).read_bytes().decode("utf-8")
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
