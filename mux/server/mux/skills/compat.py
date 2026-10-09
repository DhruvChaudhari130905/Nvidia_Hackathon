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
