
"""Plan rules: every change goes through plans.apply."""

import pytest

from mux.rooms import plan as plans


def task(id, status="draft", **extra):
    return {"id": id, "title": f"Task {id}", "status": status, **extra}


def drafted(*items):
    return plans.apply((), "plan.drafted", {"items": list(items)})


def test_draft_and_edit_replace_the_plan():
    plan = drafted(task("t1"), task("t2"))
    assert [i.id for i in plan] == ["t1", "t2"]
    plan = plans.apply(plan, "plan.edited", {"items": [task("t2"), task("t3")]})
    assert [i.id for i in plan] == ["t2", "t3"]


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        drafted(task("t1"), task("t1"))
    with pytest.raises(ValueError):
        plans.apply(drafted(task("t1")), "plan.item_added", task("t1"))


def test_approve_turns_only_drafts_into_todo():
    plan = plans.apply(drafted(task("t1"), task("t2", "done")), "plan.approved", {})
    assert [i.status for i in plan] == ["todo", "done"]
    with pytest.raises(ValueError):
        plans.apply(plan, "plan.approved", {})  # nothing left to approve


def test_item_added_appends():
    plan = plans.apply(drafted(task("t1")), "plan.item_added", task("t2", "todo"))
    assert [(i.id, i.status) for i in plan] == [("t1", "draft"), ("t2", "todo")]


def test_item_updated_merges_changes():
    plan = plans.apply(drafted(task("t1")), "plan.item_updated", {"id": "t1", "changes": {"notes": "use Tailwind"}})
    assert plan[0].notes == "use Tailwind"
    assert plan[0].title == "Task t1"


@pytest.mark.parametrize("changes", [{"id": "t9"}, {"status": "finished"}, {"title": ""}, {"color": "red"}])
def test_item_updated_rejects_bad_changes(changes):
    with pytest.raises(ValueError):
        plans.apply(drafted(task("t1")), "plan.item_updated", {"id": "t1", "changes": changes})


def test_item_updated_unknown_task():
    with pytest.raises(ValueError):
        plans.apply(drafted(task("t1")), "plan.item_updated", {"id": "t9", "changes": {"notes": "x"}})


def test_task_moves_todo_doing_done():
    plan = drafted(task("t1", "todo"))
    plan = plans.apply(plan, "task.started", {"task_id": "t1"})
    assert plan[0].status == "doing"
    plan = plans.apply(plan, "task.finished", {"task_id": "t1"})
    assert plan[0].status == "done"
    with pytest.raises(ValueError):
        plans.apply(plan, "task.finished", {"task_id": "t1"})  # already done


def test_draft_task_cannot_start():
    with pytest.raises(ValueError):
        plans.apply(drafted(task("t1")), "task.started", {"task_id": "t1"})


def test_other_events_leave_the_plan_alone():
    plan = drafted(task("t1"))
    assert plans.apply(plan, "message.posted", {"text": "hi"}) is plan


def test_bad_payload_raises():
    with pytest.raises(ValueError):
        plans.apply((), "plan.item_added", {"id": "t1"})  # no title
