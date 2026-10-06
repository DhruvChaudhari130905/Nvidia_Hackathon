"""The room plan: an ordered list of tasks, and the rules every change to it follows.

`apply` is the only way the plan changes, live and on replay. The actor computes the new plan with it before
writing the event, so a stored event always applies cleanly and replaying the log rebuilds the same plan.
"""

from collections.abc import Callable
from typing import Any

from mux.events.models import PlanItem, PlanItems, PlanItemUpdated, PlanStatus, TaskRef

Plan = tuple[PlanItem, ...]


def apply(plan: Plan, type: str, payload: dict[str, Any]) -> Plan:
    """The plan after one event; other event types leave it unchanged. Raises ValueError when a rule is broken."""
    if type in ("plan.drafted", "plan.edited"):
        return _unique(tuple(PlanItems.model_validate(payload).items))
    if type == "plan.approved":
        if not any(item.status == "draft" for item in plan):
            raise ValueError("the plan has no draft tasks to approve")
        return tuple(item.model_copy(update={"status": "todo"}) if item.status == "draft" else item for item in plan)
    if type == "plan.item_added":
        return _unique((*plan, PlanItem.model_validate(payload)))
    if type == "plan.item_updated":
        update = PlanItemUpdated.model_validate(payload)
        if "id" in update.changes:
            raise ValueError("a task id cannot change")
        return _replace(plan, update.id, lambda item: PlanItem.model_validate({**item.model_dump(), **update.changes}))
    if type == "task.started":
        return _move(plan, TaskRef.model_validate(payload).task_id, "todo", "doing")
    if type == "task.finished":
        return _move(plan, TaskRef.model_validate(payload).task_id, "doing", "done")
    return plan


def next_id(plan: Plan) -> str:
    """An id for a new task: t1, t2, ... after the highest number in use."""
    numbers = [int(item.id[1:]) for item in plan if item.id[:1] == "t" and item.id[1:].isdigit()]
    return f"t{max(numbers, default=0) + 1}"


def current(plan: Plan) -> PlanItem | None:
    """The task in progress, if any."""
    return next((item for item in plan if item.status == "doing"), None)


def load(items: list[dict[str, Any]]) -> Plan:
    """A plan as stored in a checkpoint, back as models."""
    return _unique(tuple(PlanItem.model_validate(item) for item in items))


def _unique(items: Plan) -> Plan:
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("task ids must be unique")
    return items


def _replace(plan: Plan, task_id: str, change: Callable[[PlanItem], PlanItem]) -> Plan:
    for n, item in enumerate(plan):
        if item.id == task_id:
            return (*plan[:n], change(item), *plan[n + 1:])
    raise ValueError(f"no task {task_id!r} in the plan")


def _move(plan: Plan, task_id: str, from_status: PlanStatus, to_status: PlanStatus) -> Plan:
    """Change a task's status, but only from the status the step expects (todo -> doing -> done)."""
    def change(item: PlanItem) -> PlanItem:
        if item.status != from_status:
            raise ValueError(f"task {task_id!r} is {item.status}, not {from_status}")
        return item.model_copy(update={"status": to_status})
    return _replace(plan, task_id, change)
