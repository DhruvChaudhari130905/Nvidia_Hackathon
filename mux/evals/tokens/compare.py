"""Compare coder token usage with the naive-agent baseline."""

from __future__ import annotations

from typing import Any


def compare_tokens(
    naive_tokens: int,
    coder_tokens: int,
) -> dict[str, Any]:
    """Calculate token reduction against the naive baseline."""

    if naive_tokens < 0 or coder_tokens < 0:
        raise ValueError("token counts cannot be negative")

    if naive_tokens == 0:
        return {
            "naive_tokens": 0,
            "coder_tokens": coder_tokens,
            "reduction": 0.0,
            "target": 0.40,
            "target_met": False,
        }

    reduction = (
        naive_tokens - coder_tokens
    ) / naive_tokens

    return {
        "naive_tokens": naive_tokens,
        "coder_tokens": coder_tokens,
        "reduction": reduction,
        "target": 0.40,
        "target_met": reduction >= 0.40,
    }


def compare_tasks(
    naive: list[dict[str, Any]],
    coder: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare aggregate token usage across finished tasks."""

    naive_total = sum(
        int(item.get("total_tokens", 0))
        for item in naive
    )

    coder_total = sum(
        int(item.get("total_tokens", 0))
        for item in coder
    )

    return compare_tokens(
        naive_total,
        coder_total,
    )
