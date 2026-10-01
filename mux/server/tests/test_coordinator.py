"""Tests for the coordinator."""

import asyncio

import pytest

from mux.agents.coordinator.agent import Coordinator
from mux.agents.coordinator.planner import create_plan, insert_item, next_task_id
from mux.agents.coordinator.prompts import Message, PlanItem, RoomView
from mux.agents.coordinator.schema import AddPlanItem, CoordinatorAction, PlanDraft
from mux.agents.llm import ModelRole
from mux.replay.fake_llm import FakeLLM

ROOM = RoomView(
    plan=[PlanItem("t1", "Build the RSVP form", "doing"), PlanItem("t2", "Event list page", "todo")],
    current_task_id="t1",
    pending=[Message("m1", "Priya", "pm", "add Google login for RSVPs")],
)
NEW = Message("m2", "Dan", "eng", "no auth, keep RSVPs anonymous")
MERGE = '{"label": "merge", "rationale": "fits"}'


def classify(*script):
    llm = FakeLLM(list(script))
    decision = asyncio.run(Coordinator(llm).classify(ROOM, NEW))
    return decision, llm


def test_valid_first_try():
    d, llm = classify(MERGE)
    assert d.action.label == "merge" and d.attempts == 1 and not d.fallback
    assert llm.calls[0].role is ModelRole.SUPER
    assert llm.calls[0].schema is CoordinatorAction


def test_prompt_shows_room_state():
    _, llm = classify(MERGE)
    user = llm.calls[0].messages[1]["content"]
    assert "- [t1] Build the RSVP form (doing)  <- in progress" in user
    assert "- [m1] Priya (pm): add Google login for RSVPs" in user
    assert user.endswith("- [m2] Dan (eng): no auth, keep RSVPs anonymous")


def test_fence_and_think_are_cleaned():
    d, _ = classify('<think>hmm</think>```json\n{"label": "chat", "rationale": "q", "reply": "Postgres"}\n```')
    assert d.action.reply == "Postgres" and d.attempts == 1


def test_bad_json_retries_with_error():
    d, llm = classify("not json", MERGE)
    assert d.attempts == 2 and d.action.label == "merge"
    retry = llm.calls[1].messages
    assert retry[-2] == {"role": "assistant", "content": "not json"}
    assert "invalid" in retry[-1]["content"]


def test_unknown_ids_trigger_retry():
    bad = ('{"label": "conflict", "rationale": "r", "domain": "scope", "open_conflict": '
           '{"with_message_ids": ["m99"], "summary": "s", "options": ["a", "b"]}}')
    d, llm = classify(bad, bad.replace("m99", "m1"))
    conflict = d.action.open_conflict
    assert d.attempts == 2 and conflict is not None and conflict.with_message_ids == ["m1"]
    assert "m99" in llm.calls[1].messages[-1]["content"]


def test_two_failures_fall_back_to_queue():
    d, llm = classify("nope", "still nope")
    assert d.fallback and d.action.label == "queue"
    item = d.action.add_plan_item
    assert item is not None and item.title == NEW.text
    assert llm.remaining == 0


def test_usage_adds_up_across_attempts():
    d, _ = classify("x" * 40, MERGE)
    assert d.usage.completion_tokens == 10 + len(MERGE) // 4


def test_api_error_propagates():
    with pytest.raises(TimeoutError):
        classify(TimeoutError("down"))


# planner

PLAN = ('{"tasks": [{"title": "RSVP form", "owner_role": "design", "notes": null},'
        ' {"title": "Admin list", "owner_role": "pm", "notes": "only organizers"}]}')


def plan(*script):
    llm = FakeLLM(list(script))
    result = asyncio.run(create_plan(llm, "An RSVP app\nfor a club"))
    return result, llm


def test_create_plan_numbers_tasks_as_draft():
    r, llm = plan(PLAN)
    assert [(p.id, p.title, p.status) for p in r.items] == [("t1", "RSVP form", "draft"), ("t2", "Admin list", "draft")]
    assert r.items[0].owner_role == "design" and r.items[1].notes == "only organizers"
    assert r.attempts == 1 and not r.fallback
    assert llm.calls[0].role is ModelRole.SUPER and llm.calls[0].schema is PlanDraft
    assert "An RSVP app\nfor a club" in llm.calls[0].messages[1]["content"]


def test_create_plan_retries_empty_plan():
    r, llm = plan('{"tasks": []}', PLAN)
    assert r.attempts == 2 and len(r.items) == 2
    assert "tasks" in llm.calls[1].messages[-1]["content"]


def test_create_plan_falls_back_to_one_task():
    r, _ = plan("nope", "nope")
    assert r.fallback and [(p.id, p.title, p.status) for p in r.items] == [("t1", "An RSVP app for a club", "draft")]


CURRENT = [PlanItem("t1", "Form", "done"), PlanItem("t2", "List", "doing"), PlanItem("t3", "Export", "todo")]


def test_insert_item_after_id():
    new = insert_item(CURRENT, AddPlanItem(title="Dark mode", after_task_id="t2"))
    assert [p.id for p in new] == ["t1", "t2", "t4", "t3"]
    assert new[2].title == "Dark mode" and new[2].status == "todo"
    assert len(CURRENT) == 3


def test_insert_item_goes_to_end_when_id_missing_or_unknown():
    assert [p.id for p in insert_item(CURRENT, AddPlanItem(title="x"))][-1] == "t4"
    assert [p.id for p in insert_item(CURRENT, AddPlanItem(title="x", after_task_id="t9"))][-1] == "t4"


def test_next_task_id():
    assert next_task_id([]) == "t1"
    assert next_task_id([PlanItem("t1", "a", "done"), PlanItem("t7", "b", "todo")]) == "t8"
