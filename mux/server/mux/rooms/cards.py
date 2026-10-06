"""Conflict and question cards: what is open, rebuilt from the log like the plan.

`Cards.apply` is the only way cards change, live and on replay. The actor checks the rules (an open card,
a known option) before it writes the event, so a stored event always applies.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from mux.events.models import (
    ConflictClosed, ConflictDomain, ConflictEvidence, ConflictOpened, ConflictVote, EvidenceCitation,
    QuestionAnswered, QuestionDefaulted, QuestionOpened,
)

VOTE_S = 60  # how long a vote stays open after the research is in
RESEARCH_TIMEOUT_S = 60  # a vote whose research never finished (the server stopped) opens without it
QUESTION_S = 5 * 60  # after this the coder's default becomes the answer


@dataclass
class Conflict:
    id: UUID
    message_ids: list[UUID]
    summary: str
    options: list[str]
    domain: ConflictDomain
    task_ids: list[str]
    opened_at: datetime
    expires_at: datetime | None = None  # None while the research runs
    evidence: str | None = None
    citations: list[EvidenceCitation] = field(default_factory=list)
    votes: dict[UUID, str] = field(default_factory=dict)  # user -> option
    result: str | None = None  # set when closed
    resolved_by: str | None = None
    totals: dict[str, int] = field(default_factory=dict)
    owner_asked: bool = False  # a tie was reported to the owner (memory only: asked again after a restart)

    @property
    def open(self) -> bool:
        return self.result is None


@dataclass
class Question:
    id: UUID
    task_id: str | None
    text: str
    options: list[str]
    default: str
    expires_at: datetime
    answer: str | None = None  # set when answered or defaulted
    defaulted: bool = False

    @property
    def open(self) -> bool:
        return self.answer is None


@dataclass
class Cards:
    conflicts: dict[UUID, Conflict] = field(default_factory=dict)
    questions: dict[UUID, Question] = field(default_factory=dict)

    def apply(self, type: str, payload: dict[str, Any], ts: datetime) -> None:
        """Apply one event; other event types change nothing."""
        if type == "conflict.opened":
            o = ConflictOpened.model_validate(payload)
            self.conflicts[o.id] = Conflict(o.id, o.message_ids, o.summary, o.options, o.domain, o.task_ids, ts)
        elif type == "conflict.evidence":
            e = ConflictEvidence.model_validate(payload)
            c = self.conflicts[e.conflict_id]
            c.evidence, c.citations, c.expires_at = e.summary, e.citations, e.expires_at
        elif type == "conflict.vote":
            v = ConflictVote.model_validate(payload)
            self.conflicts[v.conflict_id].votes[v.user_id] = v.option
        elif type == "conflict.closed":
            closed = ConflictClosed.model_validate(payload)
            c = self.conflicts[closed.conflict_id]
            c.result, c.resolved_by, c.totals = closed.result, closed.resolved_by, closed.totals
        elif type == "question.opened":
            q = QuestionOpened.model_validate(payload)
            self.questions[q.id] = Question(q.id, q.task_id, q.text, q.options, q.default, q.expires_at)
        elif type == "question.answered":
            a = QuestionAnswered.model_validate(payload)
            self.questions[a.question_id].answer = a.answer
        elif type == "question.defaulted":
            d = QuestionDefaulted.model_validate(payload)
            question = self.questions[d.question_id]
            question.answer, question.defaulted = d.answer, True

    def open_conflict(self, conflict_id: UUID) -> Conflict:
        """An open conflict. KeyError if unknown, ValueError if already closed."""
        conflict = self.conflicts[conflict_id]
        if not conflict.open:
            raise ValueError("this vote is closed")
        return conflict

    def open_question(self, question_id: UUID) -> Question:
        """An open question. KeyError if unknown, ValueError if already answered."""
        question = self.questions[question_id]
        if not question.open:
            raise ValueError("this question is already answered")
        return question
