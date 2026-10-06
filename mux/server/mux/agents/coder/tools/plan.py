"""update_plan: split the current task into smaller tasks of the room's plan."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

MIN_SPLIT = 2
MAX_SPLIT = 5

# (task id, subtask titles) -> the new task ids; the room's plan stores the change as an event
SplitTask = Callable[[str, list[str]], Awaitable[list[str]]]


class PlanTool:
    """The coder may change only its current task, and only by splitting it."""

    def __init__(self, current_task_id: str, split_task: SplitTask) -> None:
        self.current_task_id = current_task_id
        self._split_task = split_task

    async def split(self, task_id: str, split: list[str]) -> dict[str, Any]:
        """Replace the current task with 2 to 5 subtasks; the coder keeps working on the first."""
        if task_id != self.current_task_id:
            return {"ok": False, "error": "you can only split the current task",
                    "current_task_id": self.current_task_id}
        titles = [title.strip() for title in split if isinstance(title, str) and title.strip()]
        if not MIN_SPLIT <= len(titles) <= MAX_SPLIT:
            return {"ok": False, "error": f"split needs {MIN_SPLIT} to {MAX_SPLIT} subtasks"}
        ids = await self._split_task(task_id, titles)
        return {"ok": True, "tasks": [{"id": i, "title": t} for i, t in zip(ids, titles)], "current_task_id": ids[0]}
