"""Kickoff questions: what to ask the team before planning (the brainstorming step of "Plan it with me")."""

from __future__ import annotations

from typing import Optional

from mux.agents.coordinator.agent import ask_json
from mux.agents.coordinator.schema import KickoffQuestions
from mux.agents.llm import LLM, ModelRole, Usage

KICKOFF_SYSTEM = """You help a team decide what to build before any code changes.
From the idea and the project summary, ask 2 or 3 questions whose answers would change the plan most:
audience, scope of the first version, keep or change the existing design, must-have features.
Each question has 2 to 4 short options and a default (the safest choice). Don't ask what the summary already answers.
Answer with JSON only:
{"questions": [{"question": "...", "options": ["..."], "default": "..."}]}"""


async def ask_kickoff_questions(llm: LLM, description: str, summary: str) -> tuple[Optional[KickoffQuestions], Usage]:
    """The questions to ask, or None when the model's answers weren't usable twice (plan without them)."""
    messages = [
        {"role": "system", "content": KICKOFF_SYSTEM},
        {"role": "user", "content": f"Idea:\n{description or '(none given)'}\n\nProject summary:\n{summary or '(no files yet)'}"},
    ]
    result = await ask_json(llm, ModelRole.LIGHTNING, messages, KickoffQuestions, max_tokens=600)
    return result.value, result.usage
