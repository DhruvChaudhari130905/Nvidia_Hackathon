"""create_plan (Super) drafts the first task list; add_plan_item places queued requests in the plan."""

from __future__ import annotations

from dataclasses import dataclass

from mux.agents.coordinator.agent import ask_json
from mux.agents.coordinator.prompts import PlanItem
from mux.agents.coordinator.schema import AddPlanItem, PlanDraft, PlanItemDraft
from mux.agents.llm import LLM, ModelRole, Usage

PLAN_SYSTEM = """You plan the build of a small web app for a team. A coding agent builds it task by task, on a full-stack starter template that already runs.

Write 3 to 8 tasks, in build order:
- Each task is one feature the team can see in the preview when it is done.
- The first task builds the smallest working version of the main screen.
- No setup tasks: the stack, tools, and hosting are already chosen.
- "title": short and imperative, under 60 characters.
- "notes": one sentence of detail, or null.
- "owner_role": who cares most about the task, "pm", "design" or "eng", or null.

Answer with JSON only:
{"tasks": [{"title": "...", "owner_role": null, "notes": null}]}"""


@dataclass
class PlanResult:
    items: list[PlanItem]
    usage: Usage
    attempts: int
    fallback: bool = False  # True when the model failed twice and a one-task plan was used


async def create_plan(llm: LLM, description: str, *, reasoning: bool | None = None) -> PlanResult:
    # always Super: plan quality matters and it runs once per room
    messages = [
        {"role": "system", "content": PLAN_SYSTEM},
        {"role": "user", "content": f"App description:\n{description}"},
    ]
    result = await ask_json(llm, ModelRole.SUPER, messages, PlanDraft, reasoning=reasoning, max_tokens=1200)
    if result.value is None:
        # the plan is still a draft, so the team can fix a one-task plan before approving
        draft = PlanDraft(tasks=[PlanItemDraft(title=_short_title(description))])
        return PlanResult(_numbered(draft), result.usage, result.attempts, fallback=True)
    return PlanResult(_numbered(result.value), result.usage, result.attempts)


def insert_item(plan: list[PlanItem], item: AddPlanItem, status: str = "todo") -> list[PlanItem]:
    """Return a new plan with the item after after_task_id, or at the end when that id is unknown."""
    new = PlanItem(next_task_id(plan), item.title, status)
    ids = [p.id for p in plan]
    at = ids.index(item.after_task_id) + 1 if item.after_task_id in ids else len(plan)
    return [*plan[:at], new, *plan[at:]]


def next_task_id(plan: list[PlanItem]) -> str:
    numbers = [int(p.id[1:]) for p in plan if p.id[1:].isdigit()]
    return f"t{max(numbers, default=0) + 1}"


def _numbered(draft: PlanDraft) -> list[PlanItem]:
    return [
        PlanItem(f"t{i}", task.title, "draft", task.owner_role, task.notes)
        for i, task in enumerate(draft.tasks, start=1)
    ]


def _short_title(description: str) -> str:
    return " ".join(description.split())[:60] or "Build the app"
