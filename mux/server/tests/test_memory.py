
"""Tests for task logs, day logs, and pins."""

import asyncio
import json

from mux.agents.coordinator.conflicts import Tally
from mux.agents.coordinator.prompts import PlanItem
from mux.agents.llm import ModelRole
from mux.memory.day_log import write_day_log
from mux.memory.pins import Pin, merge_pins, pin_override, pin_vote
from mux.memory.task_log import LOG_CHAR_LIMIT, Log, LogDraft, write_task_log
from mux.replay.fake_llm import FakeLLM

TASK = PlanItem("t2", "Admin list", "done")
PLAN = [PlanItem("t1", "RSVP form", "done"), TASK, PlanItem("t3", "CSV export", "todo")]
PREVIOUS = Log(LogDraft(app="An RSVP app.", changed=["Built the form"], conventions=["API routes under /api"]),
               [Pin("vote", "c1", "Login: the team chose 'Anonymous'")])
DRAFT = LogDraft(app="An RSVP app with an admin list.", changed=["Added /admin"], open_threads=["CSV export"],
                 conventions=["API routes under /api"])


def task_log(*script, previous: Log | None = PREVIOUS, new_pins: list[Pin] | None = None):
    llm = FakeLLM(list(script))
    result = asyncio.run(write_task_log(llm, previous, TASK, ["Added /admin page", "Build passed"], PLAN, new_pins))
    return result, llm


# pins

def test_pin_vote_and_tie():
    pin = pin_vote("c1", "Login", Tally("Anonymous", {"Google login": 1, "Anonymous": 1}, "owner"))
    assert pin is not None and pin.text == "Login: the team chose 'Anonymous' (Google login 1, Anonymous 1, tie broken by owner)"
    assert pin_vote("c1", "Login", Tally(None, {"a": 1, "b": 1}, "tie")) is None


def test_override_replaces_vote_in_place():
    vote, other = Pin("vote", "c1", "old"), Pin("vote", "c2", "other")
    merged = merge_pins([vote, other], [pin_override("c1", "Login", "Google login")])
    assert [p.conflict_id for p in merged] == ["c1", "c2"]
    assert merged[0].kind == "override" and "owner chose 'Google login'" in merged[0].text


# task log

def test_task_log_rolls_previous_and_keeps_pins():
    r, llm = task_log(DRAFT)
    assert r.log.draft == DRAFT and r.attempts == 1 and not r.fallback
    assert r.log.pins == PREVIOUS.pins
    assert r.log.body.endswith("Pinned team decisions (do not change these):\n- Login: the team chose 'Anonymous'")
    user = llm.calls[0].messages[1]["content"]
    assert "App: An RSVP app." in user and "Task just finished: [t2] Admin list" in user
    assert "- Added /admin page" in user and "- [t3] CSV export (todo)" in user
    assert "Login" not in user  # the model never sees pins, so it cannot reword them
    assert llm.calls[0].schema is LogDraft and llm.calls[0].role is ModelRole.SUPER


def test_task_log_adds_new_pins():
    new = Pin("override", "c2", "Pages: the owner chose 'one page'")
    r, _ = task_log(DRAFT, new_pins=[new])
    assert [p.conflict_id for p in r.log.pins] == ["c1", "c2"]


def test_first_task_log_has_no_previous():
    r, llm = task_log(DRAFT, previous=None)
    assert "(none, this was the first task)" in llm.calls[0].messages[1]["content"] and r.log.pins == []


def test_too_long_log_is_retried():
    huge = DRAFT.model_copy(update={"app": "x" * (LOG_CHAR_LIMIT + 1)})
    r, llm = task_log(huge.model_dump_json(), DRAFT)
    assert r.attempts == 2 and r.log.draft == DRAFT
    assert f"keep it under {LOG_CHAR_LIMIT}" in llm.calls[1].messages[-1]["content"]


def test_task_log_fallback_keeps_old_log_and_adds_changes():
    r, _ = task_log("nope", "nope")
    assert r.fallback and r.log.pins == PREVIOUS.pins
    assert r.log.draft.app == "An RSVP app." and r.log.draft.conventions == ["API routes under /api"]
    assert r.log.draft.changed == ["Finished: Admin list", "Added /admin page", "Build passed"]


# day log

def test_day_log_compacts_all_logs_and_merges_pins():
    later = Log(DRAFT, [Pin("override", "c1", "Login: the owner chose 'Google login'"), Pin("vote", "c3", "Theme: dark")])
    llm = FakeLLM([json.dumps({"app": "Day summary."})])
    r = asyncio.run(write_day_log(llm, PREVIOUS, [PREVIOUS, later]))
    assert r.log.draft.app == "Day summary."
    assert [(p.conflict_id, p.kind) for p in r.log.pins] == [("c1", "override"), ("c3", "vote")]
    user = llm.calls[0].messages[1]["content"]
    assert user.index("Previous day log:") < user.index("Task log 1:") < user.index("Task log 2:")


def test_day_log_fallback_uses_latest_task_log():
    r = asyncio.run(write_day_log(FakeLLM(["nope", "nope"]), None, [PREVIOUS, Log(DRAFT)]))
    assert r.fallback and r.log.draft == DRAFT


def test_day_log_with_no_tasks_keeps_previous_without_a_call():
    llm = FakeLLM()
    r = asyncio.run(write_day_log(llm, PREVIOUS, []))
    assert r.log is PREVIOUS and r.attempts == 0 and llm.calls == []
    assert asyncio.run(write_day_log(llm, None, [])).log.draft.app == "Nothing built yet."


