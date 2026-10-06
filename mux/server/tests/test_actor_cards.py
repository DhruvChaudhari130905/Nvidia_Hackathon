"""RoomActor cards: conflict votes (weights, closing, ties, override, timeout) and questions."""

from datetime import timedelta
from uuid import uuid4

import pytest

from mux.events.models import PlanItem
from mux.rooms.actor import RoomActor
from mux.rooms.cards import RESEARCH_TIMEOUT_S, VOTE_S


@pytest.fixture
def published():
    return []


@pytest.fixture
def publish(published):
    async def _publish(event):
        published.append(event)
    return _publish


async def new_room(session_factory, publish, owner, *statuses, domain_role=None):
    actor = await RoomActor.create(owner, "Todo app", publish, template={}, domain_role=domain_role,
                                   sessionmaker=session_factory)
    items = [PlanItem(id=f"t{n}", title=f"Task {n}", status=s) for n, s in enumerate(statuses, start=1)]
    if items:
        await actor.draft_plan(items, "owner")
    return actor


async def conflict_on_t1(actor, owner, domain="ui"):
    """A conflict whose clashing message was queued as t1, with the vote open."""
    message = await actor.post_message(owner, "use a sidebar")
    await actor.label_message(message.id, "queue", "new work", task_id="t1")
    card = await actor.open_conflict([message.id], "Sidebar or top bar?", ["Sidebar", "Top bar"], domain, "use a top bar")
    await actor.start_vote(card.id)
    return card


def statuses(actor):
    return [item.status for item in actor.plan]


async def test_open_holds_the_linked_todo_task(session_factory, publish, published):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, "todo", "todo")
    card = await conflict_on_t1(actor, owner)
    assert statuses(actor) == ["skipped_conflict", "todo"]
    assert card.task_ids == ["t1"] and card.open and card.expires_at is not None
    assert [e.type for e in published][-3:] == ["conflict.opened", "plan.item_updated", "conflict.evidence"]


async def test_everyone_voting_closes_with_role_weights(session_factory, publish, published):
    owner, designer = uuid4(), uuid4()
    actor = await new_room(session_factory, publish, owner, "todo")
    await actor.set_member(designer, "editor", owner, "design")
    card = await conflict_on_t1(actor, owner, domain="ui")
    await actor.vote(card.id, owner, "Sidebar")
    assert card.open
    await actor.vote(card.id, designer, "Top bar")  # design owns ui: 2 beats 1
    assert (card.result, card.resolved_by) == ("Top bar", "votes")
    closed = next(e for e in published if e.type == "conflict.closed")
    assert closed.payload["totals"] == {"Sidebar": 1, "Top bar": 2}
    assert actor.plan[0].status == "todo"
    assert actor.plan[0].merged_notes == ['The team chose "Top bar" for: Sidebar or top bar?']


async def test_a_later_vote_replaces_the_earlier_one(session_factory, publish):
    owner, mate = uuid4(), uuid4()
    actor = await new_room(session_factory, publish, owner, "todo")
    await actor.set_member(mate, "editor", owner)
    card = await conflict_on_t1(actor, owner)
    await actor.vote(card.id, mate, "Sidebar")
    await actor.vote(card.id, mate, "Top bar")
    assert card.votes == {mate: "Top bar"} and card.open


async def test_bad_votes_are_refused(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, "todo")
    card = await conflict_on_t1(actor, owner)
    with pytest.raises(ValueError):
        await actor.vote(card.id, owner, "Hamburger")
    with pytest.raises(KeyError):
        await actor.vote(uuid4(), owner, "Sidebar")
    await actor.override(card.id, "Sidebar", owner)
    with pytest.raises(ValueError, match="closed"):
        await actor.vote(card.id, owner, "Top bar")


async def test_owner_override_wins_over_votes(session_factory, publish):
    owner, mate = uuid4(), uuid4()
    actor = await new_room(session_factory, publish, owner, "todo")
    await actor.set_member(mate, "editor", owner, "design")
    card = await conflict_on_t1(actor, owner)
    await actor.vote(card.id, mate, "Top bar")
    await actor.override(card.id, "Sidebar", owner)
    assert (card.result, card.resolved_by) == ("Sidebar", "override")


async def test_timeout_closes_by_tally(session_factory, publish):
    owner, mate, other = uuid4(), uuid4(), uuid4()
    actor = await new_room(session_factory, publish, owner, "todo")
    await actor.set_member(mate, "editor", owner)
    await actor.set_member(other, "editor", owner)
    card = await conflict_on_t1(actor, owner)
    await actor.vote(card.id, mate, "Sidebar")
    await actor.tick(now=card.expires_at - timedelta(seconds=1))
    assert card.open
    await actor.tick(now=card.expires_at)
    assert (card.result, card.resolved_by) == ("Sidebar", "votes")


async def test_a_tie_stays_open_and_asks_the_owner_once(session_factory, publish, published):
    owner, eng1, eng2 = uuid4(), uuid4(), uuid4()
    actor = await new_room(session_factory, publish, owner, "todo")
    await actor.set_member(eng1, "editor", owner, "eng")
    await actor.set_member(eng2, "editor", owner, "eng")
    card = await conflict_on_t1(actor, owner, domain="scope")
    await actor.vote(card.id, eng1, "Sidebar")
    await actor.vote(card.id, eng2, "Top bar")
    await actor.tick(now=card.expires_at)
    await actor.tick(now=card.expires_at + timedelta(seconds=10))
    assert card.open and actor.plan[0].status == "skipped_conflict"
    asks = [e for e in published if e.type == "coordinator.reply" and "tied" in e.payload["text"]]
    assert len(asks) == 1


async def test_vote_opens_without_research_after_a_timeout(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, "todo")
    card = await actor.open_conflict([], "A or B?", ["A", "B"], "ui", "use B")
    await actor.tick(now=card.opened_at + timedelta(seconds=RESEARCH_TIMEOUT_S - 1))
    assert card.expires_at is None
    later = card.opened_at + timedelta(seconds=RESEARCH_TIMEOUT_S + 1)
    await actor.tick(now=later)
    assert card.expires_at == later + timedelta(seconds=VOTE_S)


async def test_result_goes_back_as_draft_while_the_plan_awaits_approval(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, "draft")
    card = await actor.open_conflict([], "A or B?", ["A", "B"], "ui", "use B")
    assert statuses(actor) == ["draft", "skipped_conflict"]
    await actor.override(card.id, "B", owner)
    assert statuses(actor) == ["draft", "draft"]


async def test_question_holds_the_task_until_answered(session_factory, publish):
    owner, mate = uuid4(), uuid4()
    actor = await new_room(session_factory, publish, owner, "todo")
    await actor.set_member(mate, "editor", owner)
    await actor.start_task("t1")
    question = await actor.open_question("t1", "Stripe or fake checkout?", ["Stripe", "Fake"], "Fake")
    assert statuses(actor) == ["skipped_question"]
    with pytest.raises(ValueError):
        await actor.answer_question(question.id, "PayPal", mate)
    await actor.answer_question(question.id, "Stripe", mate)
    assert question.answer == "Stripe" and not question.defaulted
    assert statuses(actor) == ["todo"]
    assert actor.plan[0].merged_notes == ['The room answered "Stripe or fake checkout?": Stripe']
    with pytest.raises(ValueError, match="already answered"):
        await actor.answer_question(question.id, "Fake", mate)


async def test_unanswered_question_takes_the_default(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, "todo")
    question = await actor.open_question("t1", "Stripe or fake?", ["Stripe", "Fake"], "Fake")
    await actor.tick(now=question.expires_at - timedelta(seconds=1))
    assert question.open
    await actor.tick(now=question.expires_at)
    assert (question.answer, question.defaulted) == ("Fake", True)
    assert statuses(actor) == ["todo"]


async def test_question_rules(session_factory, publish):
    owner = uuid4()
    actor = await new_room(session_factory, publish, owner, "todo")
    with pytest.raises(ValueError, match="default"):
        await actor.open_question("t1", "?", ["A", "B"], "C")
    with pytest.raises(ValueError, match="no task"):
        await actor.open_question("t9", "?", ["A", "B"], "A")


async def test_cards_are_rebuilt_when_the_room_reopens(session_factory, publish):
    owner, mate = uuid4(), uuid4()
    actor = await new_room(session_factory, publish, owner, "todo", "todo")
    await actor.set_member(mate, "editor", owner)
    card = await conflict_on_t1(actor, owner)
    await actor.vote(card.id, mate, "Top bar")
    question = await actor.open_question("t2", "Stripe?", ["Yes", "No"], "No")
    await actor.answer_question(question.id, "Yes", mate)

    reopened = await RoomActor.open(actor.room_id, publish, sessionmaker=session_factory)
    assert reopened is not None
    again = reopened.cards.conflicts[card.id]
    assert again.votes == {mate: "Top bar"} and again.open and again.task_ids == ["t1"]
    assert again.expires_at == card.expires_at
    assert reopened.cards.questions[question.id].answer == "Yes"
    assert [item.status for item in reopened.plan] == ["skipped_conflict", "todo"]
