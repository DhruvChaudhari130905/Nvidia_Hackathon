"""The room's coordinator worker: messages to the agent are labeled and carried out through the actor."""

import asyncio
from uuid import uuid4

import pytest

from mux.agents.coordinator.schema import (
    AddPlanItem, Citation, CoordinatorAction, OpenConflict, PlanDraft, PlanItemDraft, ResearchSummary,
)
from mux.integrations.tavily import SearchResult, Source
from mux.events.models import PlanItem
from mux.replay.fake_llm import FakeLLM
from mux.rooms.actor import RoomActor
from mux.rooms.coordination import RoomCoordinator, room_view
from mux.rooms.registry import RoomRegistry


@pytest.fixture
def published():
    return []


@pytest.fixture
def publish(published):
    async def _publish(event):
        published.append(event)
    return _publish


async def new_room(session_factory, publish, owner, plan=None):
    actor = await RoomActor.create(owner, "Todo app", publish, description="A todo app", template={},
                                   sessionmaker=session_factory)
    if plan:
        await actor.draft_plan(plan, "owner")
    return actor


def tasks(*statuses):
    return [PlanItem(id=f"t{n}", title=f"Task {n}", status=s) for n, s in enumerate(statuses, start=1)]


def action(label, **fields):
    return CoordinatorAction(label=label, rationale="because", **fields)


def types(published, start=0):
    return [e.type for e in published[start:]]


async def test_chat_is_labeled_answered_and_charged(session_factory, publish, published):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("todo"))
    llm = FakeLLM([action("chat", reply="Yes, it uses React.")])
    message = await actor.post_message(owner, "Is this React?")
    start = len(published)
    await RoomCoordinator(actor, llm).handle(message)
    assert types(published, start) == ["budget.updated", "coordinator.reply", "message.labeled"]
    reply, labeled = published[-2].payload, published[-1].payload
    assert labeled["message_id"] == str(message.id) and labeled["label"] == "chat"
    assert reply == {"text": "Yes, it uses React.", "message_id": str(message.id)}
    assert actor.budget.tokens_used > 0
    assert actor.recent[message.id].label == "chat"


async def test_first_message_drafts_the_plan(session_factory, publish, published):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner)
    llm = FakeLLM([PlanDraft(tasks=[PlanItemDraft(title="Show todos"), PlanItemDraft(title="Add a todo")])])
    message = await actor.post_message(owner, "Make it pink")
    await RoomCoordinator(actor, llm).handle(message)
    assert [(p.id, p.title, p.status) for p in actor.plan] == [("t1", "Show todos", "draft"), ("t2", "Add a todo", "draft")]
    assert "A todo app" in llm.calls[0].messages[1]["content"] and "Make it pink" in llm.calls[0].messages[1]["content"]
    assert actor.recent[message.id].label == "plan"
    assert published[-1].type == "coordinator.reply"


async def test_queue_inserts_after_a_task_or_appends(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("done", "todo"))
    llm = FakeLLM([
        action("queue", add_plan_item=AddPlanItem(title="Dark mode", after_task_id="t1")),
        action("queue", add_plan_item=AddPlanItem(title="Export", after_task_id="t2")),
    ])
    coordinator = RoomCoordinator(actor, llm)
    await coordinator.handle(await actor.post_message(owner, "dark mode"))
    await coordinator.handle(await actor.post_message(owner, "export"))
    assert [(p.id, p.title, p.status) for p in actor.plan] == [
        ("t1", "Task 1", "done"), ("t3", "Dark mode", "todo"), ("t2", "Task 2", "todo"), ("t4", "Export", "todo"),
    ]


async def test_queued_task_is_a_draft_while_the_plan_awaits_approval(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("draft"))
    llm = FakeLLM([action("queue", add_plan_item=AddPlanItem(title="Login"))])
    await RoomCoordinator(actor, llm).handle(await actor.post_message(owner, "add login"))
    assert actor.plan[-1].status == "draft"


async def test_merge_and_interrupt_add_notes_to_the_task_in_progress(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("todo"))
    await actor.start_task("t1")
    llm = FakeLLM([action("merge"), action("interrupt")])
    coordinator = RoomCoordinator(actor, llm)
    await coordinator.handle(await actor.post_message(owner, "make the button blue"))
    assert not actor.interrupt_requested
    await coordinator.handle(await actor.post_message(owner, "stop, use a table instead"))
    assert actor.plan[0].merged_notes == ["make the button blue", "stop, use a table instead"]
    assert actor.interrupt_requested


async def test_merge_with_nothing_in_progress_becomes_a_task(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("todo"))
    llm = FakeLLM([action("merge")])
    await RoomCoordinator(actor, llm).handle(await actor.post_message(owner, "make the button blue"))
    assert [p.title for p in actor.plan] == ["Task 1", "make the button blue"]


async def test_queue_and_merge_labels_name_their_task(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("todo"))
    await actor.start_task("t1")
    llm = FakeLLM([action("queue", add_plan_item=AddPlanItem(title="Login")), action("merge")])
    coordinator = RoomCoordinator(actor, llm)
    queued = await actor.post_message(owner, "add login")
    await coordinator.handle(queued)
    merged = await actor.post_message(owner, "blue button")
    await coordinator.handle(merged)
    assert (actor.recent[queued.id].task_id, actor.recent[merged.id].task_id) == ("t2", "t1")


class FakeSearch:
    def __init__(self, sources):
        self.sources = sources
        self.queries = []

    async def search(self, query):
        self.queries.append(query)
        return SearchResult(query, "Both work.", self.sources)


async def test_conflict_opens_a_card_holds_the_task_and_researches(session_factory, publish, published):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("done"))
    first = await actor.post_message(owner, "use a sidebar")
    await actor.label_message(first.id, "queue", "new work", task_id="t2")
    await actor.add_plan_item(PlanItem(id="t2", title="Sidebar", status="todo"), "agent")
    conflict = OpenConflict(with_message_ids=["m1"], summary="Sidebar or top bar?", options=["Sidebar", "Top bar"],
                            research_queries=["sidebar vs top bar navigation"])
    summary = ResearchSummary(summary="Sidebars suit many sections [1].",
                              citations=[Citation(title="Nav", url="https://nav.example")])
    llm = FakeLLM([action("conflict", domain="ui", open_conflict=conflict), summary])
    search = FakeSearch([Source("Nav", "https://nav.example", "...")])
    second = await actor.post_message(owner, "use a top bar")
    await RoomCoordinator(actor, llm, search).handle(second)

    [card] = actor.cards.conflicts.values()
    assert card.message_ids == [first.id] and card.task_ids == ["t2"] and card.domain == "ui"
    assert actor.plan[1].status == "skipped_conflict"
    assert search.queries == ["sidebar vs top bar navigation"]
    assert card.evidence == "Sidebars suit many sections [1]." and card.expires_at is not None
    assert [c.url for c in card.citations] == ["https://nav.example"]
    assert types(published)[-3:] == ["budget.updated", "conflict.evidence", "message.labeled"]


async def test_conflict_without_search_opens_the_vote_at_once(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("todo"))
    conflict = OpenConflict(with_message_ids=["m1"], summary="Auth or not?", options=["Google login", "Anonymous"])
    llm = FakeLLM([action("conflict", domain="scope", open_conflict=conflict)])
    message = await actor.post_message(owner, "keep it anonymous")
    await RoomCoordinator(actor, llm).handle(message)
    [card] = actor.cards.conflicts.values()
    assert card.evidence is None and card.expires_at is not None
    # nothing linked was waiting, so a new held task carries the result
    assert [(p.title, p.status) for p in actor.plan][-1] == ("keep it anonymous", "skipped_conflict")


async def test_view_uses_short_ids_pending_requests_and_team_notes(session_factory, publish):
    owner, mate = uuid4(), uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("todo"))
    await actor.set_member(mate, "editor", owner, "design")
    await actor.connect(mate, "Ana")
    asked = await actor.post_message(owner, "add a footer")
    await actor.label_message(asked.id, "queue", "new work")
    chatted = await actor.post_message(owner, "hi?")
    await actor.label_message(chatted.id, "chat", "small talk")
    await actor.post_message(mate, "I prefer dark colors", to="team")
    new = await actor.post_message(mate, "make it dark")
    view, message, ids = room_view(actor, new)
    assert [(m.id, m.text) for m in view.pending] == [("m1", "add a footer")]
    assert (message.id, message.author, message.role) == ("m2", "Ana", "design")
    assert ids == {"m1": asked.id, "m2": new.id}
    assert [n.text for n in view.team_notes] == ["I prefer dark colors"]
    assert view.open_cards == []
    await actor.open_conflict([], "Dark or light?", ["Dark", "Light"], "ui", "make it dark")
    await actor.open_question("t1", "Serif?", ["Yes", "No"], "No")
    view, _, _ = room_view(actor, new)
    assert view.open_cards == ["vote: Dark or light? (Dark / Light)", "question: Serif? (Yes / No)"]


async def test_paused_room_answers_without_the_model(session_factory, publish, published):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("todo"))
    await actor.set_budget_caps(1, 10, str(owner))
    await actor.charge(tokens=1)
    llm = FakeLLM()
    message = await actor.post_message(owner, "add login")
    await RoomCoordinator(actor, llm).handle(message)
    assert llm.calls == []
    assert "paused" in published[-1].payload["text"]
    assert actor.unhandled() == [message]


async def test_worker_survives_a_model_error(session_factory, publish, published):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("todo"))
    llm = FakeLLM([RuntimeError("model down"), action("chat", reply="ok")])
    coordinator = RoomCoordinator(actor, llm)
    coordinator.start()
    try:
        first = await actor.post_message(owner, "one")
        second = await actor.post_message(owner, "two")
        await asyncio.wait_for(coordinator.queue.join(), 5)
    finally:
        await coordinator.stop()
    replies = [e.payload for e in published if e.type == "coordinator.reply"]
    assert replies[0]["message_id"] == str(first.id) and "send it again" in replies[0]["text"]
    assert replies[1] == {"text": "ok", "message_id": str(second.id)}
    assert actor.on_agent_message is None


async def test_team_messages_skip_the_coordinator(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("todo"))
    coordinator = RoomCoordinator(actor, FakeLLM())
    coordinator.start()
    try:
        await actor.post_message(owner, "lunch?", to="team")
        assert coordinator.queue.empty()
    finally:
        await coordinator.stop()


async def test_unlabeled_messages_run_when_the_room_reopens(session_factory, publish, published):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, tasks("draft"))  # a draft plan keeps the coder idle
    done = await actor.post_message(owner, "hi")
    await actor.label_message(done.id, "chat", "small talk")
    lost = await actor.post_message(owner, "add login")  # the server stopped before the coordinator got to it

    registry = RoomRegistry(publish, sessionmaker=session_factory,
                            llm=FakeLLM([action("queue", add_plan_item=AddPlanItem(title="Login"))]))
    reopened = await registry.get(actor.room_id)
    assert reopened is not None
    assert reopened.recent[done.id].label == "chat"
    try:
        await asyncio.wait_for(registry._coordinators[actor.room_id].queue.join(), 5)
    finally:
        await registry.close()
    assert reopened.recent[lost.id].label == "queue"
    assert reopened.plan[-1].title == "Login"
