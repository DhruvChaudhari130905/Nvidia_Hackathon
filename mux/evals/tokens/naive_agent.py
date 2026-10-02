"""Naive agent baseline used for token-efficiency comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NaiveAgentResult:
    """Token usage for one naive-agent task."""

    task_id: str
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


class NaiveAgent:
    """Baseline that keeps full context without compaction."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.results: list[NaiveAgentResult] = []

    def add_message(self, message: dict[str, Any]) -> None:
        self.messages.append(dict(message))

    def record(
        self,
        task_id: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> NaiveAgentResult:
        result = NaiveAgentResult(
            task_id=task_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        self.results.append(result)
        return result

    def context(self) -> list[dict[str, Any]]:
        """Return the complete uncompressed conversation history."""
        return list(self.messages)

    def total_tokens(self) -> int:
        return sum(
            result.total_tokens
            for result in self.results
        )
