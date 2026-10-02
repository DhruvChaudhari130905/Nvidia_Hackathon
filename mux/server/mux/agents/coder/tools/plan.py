"""update_plan: mark the current task or split it into smaller tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


# the plan statuses from architecture section 3 that the coder may set
_ALLOWED_STATUSES = {
    "todo",
    "doing",
    "done",
}


@dataclass
class PlanTask:
    """One task in the coder's local plan."""

    id: str
    title: str
    status: str = "todo"


@dataclass
class Plan:
    """Minimal mutable plan used by the coder tool."""

    tasks: list[PlanTask] = field(default_factory=list)


class PlanTool:
    """Update only the current task or split it into subtasks."""

    def __init__(
        self,
        tasks: Iterable[PlanTask] = (),
    ) -> None:
        self.plan = Plan(list(tasks))

    def update_plan(
        self,
        *,
        task_id: str,
        status: str | None = None,
        split: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update a task status or replace it with smaller subtasks."""
        if status is None and split is None:
            return {
                "ok": False,
                "error": "provide status or split",
            }

        if status is not None and split is not None:
            return {
                "ok": False,
                "error": "use status or split, not both",
            }

        task = self._find(task_id)

        if task is None:
            return {
                "ok": False,
                "error": "current task not found",
                "task_id": task_id,
            }

        if status is not None:
            normalized = status.strip().lower()

            if normalized not in _ALLOWED_STATUSES:
                return {
                    "ok": False,
                    "error": "invalid status",
                    "allowed_statuses": sorted(
                        _ALLOWED_STATUSES
                    ),
                }

            task.status = normalized

            return {
                "ok": True,
                "action": "status",
                "task": _task_dict(task),
            }

        subtasks = [
            title.strip()
            for title in (split or [])
            if title.strip()
        ]

        if len(subtasks) < 2:
            return {
                "ok": False,
                "error": "split requires at least 2 subtasks",
            }

        self.plan.tasks = [
            item
            for item in self.plan.tasks
            if item.id != task_id
        ]

        created: list[PlanTask] = []

        for index, title in enumerate(subtasks, start=1):
            subtask = PlanTask(
                id=f"{task.id}.{index}",
                title=title,
                status="todo",
            )
            created.append(subtask)

        self.plan.tasks.extend(created)

        return {
            "ok": True,
            "action": "split",
            "replaced_task": task_id,
            "tasks": [
                _task_dict(item)
                for item in created
            ],
        }

    def get_plan(self) -> dict[str, Any]:
        """Return the current plan."""
        return {
            "ok": True,
            "tasks": [
                _task_dict(task)
                for task in self.plan.tasks
            ],
        }

    def _find(self, task_id: str) -> PlanTask | None:
        for task in self.plan.tasks:
            if task.id == task_id:
                return task

        return None


def _task_dict(task: PlanTask) -> dict[str, str]:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
    }


def update_plan(
    *,
    task_id: str,
    status: str | None = None,
    split: list[str] | None = None,
    plan: PlanTool | None = None,
) -> dict[str, Any]:
    """Convenience wrapper around PlanTool."""
    if plan is None:
        return {
            "ok": False,
            "error": "plan is not available",
        }

    return plan.update_plan(
        task_id=task_id,
        status=status,
        split=split,
    )
