"""JSON output schema for the coordinator actions: classify, create_plan, add_plan_item, open_conflict, research_conflict, reply."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Label = Literal["merge", "queue", "interrupt", "conflict", "chat", "review"]
Domain = Literal["ui", "architecture", "scope"]
DomainRole = Literal["pm", "design", "eng"]


class AddPlanItem(BaseModel):
    title: str
    after_task_id: str | None = None  # None puts it at the end of the plan


class OpenConflict(BaseModel):
    with_message_ids: list[str] = Field(min_length=1)
    summary: str
    options: list[str] = Field(min_length=2, max_length=4)
    research_queries: list[str] = Field(default_factory=list, max_length=3)


class Review(BaseModel):
    focus: str = Field(min_length=1, max_length=120)  # what to look at, e.g. "the whole project"


class CoordinatorAction(BaseModel):
    label: Label
    rationale: str
    domain: Domain | None = None
    add_plan_item: AddPlanItem | None = None
    open_conflict: OpenConflict | None = None
    reply: str | None = None
    review: Review | None = None

    @model_validator(mode="after")
    def _fields_match_label(self) -> CoordinatorAction:
        if self.label == "queue" and self.add_plan_item is None:
            raise ValueError("label 'queue' needs add_plan_item")
        if self.label == "conflict" and (self.open_conflict is None or self.domain is None):
            raise ValueError("label 'conflict' needs open_conflict and domain")
        if self.label == "chat" and not self.reply:
            raise ValueError("label 'chat' needs reply")
        if self.label == "review" and self.review is None:
            raise ValueError("label 'review' needs review")
        # drop fields that belong to other labels, so the actor never acts on them
        if self.label != "queue":
            self.add_plan_item = None
        if self.label != "conflict":
            self.open_conflict = None
        if self.label != "chat":
            self.reply = None
        if self.label != "review":
            self.review = None
        return self


class PlanItemDraft(BaseModel):
    title: str
    owner_role: DomainRole | None = None
    notes: str | None = None


class PlanDraft(BaseModel):
    tasks: list[PlanItemDraft] = Field(min_length=1, max_length=12)


class Citation(BaseModel):
    title: str
    url: str


class ResearchSummary(BaseModel):
    summary: str
    citations: list[Citation] = Field(min_length=1)
