"""finish_task: marks the current task done."""

from __future__ import annotations

from typing import Any


def finish_task(
    summary: str,
) -> dict[str, Any]:
    """Mark a coder task as complete with a concise summary."""
    if not isinstance(summary, str) or not summary.strip():
        return {
            "ok": False,
            "error": "summary is required",
        }

    clean_summary = " ".join(summary.split())

    result: dict[str, Any] = {
        "ok": True,
        "status": "done",
        "summary": clean_summary,
    }

    return result
