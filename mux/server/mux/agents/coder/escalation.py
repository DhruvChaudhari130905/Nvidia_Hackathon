"""Turn limits, loop detection, and escalation to Ultra."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from mux.agents.llm import ModelRole

MAX_REPEATS = 3
FAILED_BUILDS_BEFORE_ULTRA = 2


@dataclass
class EscalationState:
    """Tracks limits and escalation state for one coder task."""

    max_turns: int = 25
    model: ModelRole = ModelRole.SUPER
    turns: int = 0
    consecutive_failed_builds: int = 0
    _since_change: dict[str, int] = field(default_factory=dict)  # call -> times since the last file change
    _ultra_errors: dict[str, int] = field(default_factory=dict)

    def next_turn(self) -> bool:
        """Advance the turn counter if another turn is allowed."""
        if self.turns >= self.max_turns:
            return False
        self.turns += 1
        return True

    def record_tool_call(self, name: str, arguments: dict[str, Any]) -> bool:
        """Return True when the same call with the same arguments comes 3 times with no file change between.

        A change resets the count: build, edit, build is progress, not a loop. Reading two files in turn
        (a, b, a, b, a) with nothing changing is a loop.
        """
        if name in ("write_file", "edit_file", "delete_file", "add_image"):
            self._since_change.clear()
            return False
        key = f"{name}:{json.dumps(arguments, sort_keys=True, default=str)}"
        self._since_change[key] = self._since_change.get(key, 0) + 1
        return self._since_change[key] >= MAX_REPEATS

    def record_build(self, passed: bool) -> bool:
        """Record a build result. Return True when this result moves the task to Ultra."""
        if passed:
            self.consecutive_failed_builds = 0
            return False
        self.consecutive_failed_builds += 1
        if self.consecutive_failed_builds >= FAILED_BUILDS_BEFORE_ULTRA and self.model != ModelRole.ULTRA:
            self.model = ModelRole.ULTRA
            return True
        return False

    def record_ultra_error(self, error: str) -> bool:
        """Record a build error made on Ultra. Return True when Ultra hits the same error twice."""
        normalized = " ".join(str(error).split()) or "unknown build error"
        count = self._ultra_errors.get(normalized, 0) + 1
        self._ultra_errors[normalized] = count
        return count >= 2
