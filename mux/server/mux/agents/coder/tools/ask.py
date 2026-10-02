"""ask_room: create a question card for the room."""

from __future__ import annotations

from typing import Any


def ask_room(
    question: str,
    options: list[str],
    default: str,
) -> dict[str, Any]:
    """Validate a room question and return the card. The executor sends it to the room."""

    if not isinstance(question, str) or not question.strip():
        return {"ok": False, "error": "question is required"}

    if not isinstance(options, list) or len(options) < 2:
        return {
            "ok": False,
            "error": "at least 2 options are required",
        }

    clean_options = [
        str(option).strip()
        for option in options
        if str(option).strip()
    ]

    if len(clean_options) < 2:
        return {
            "ok": False,
            "error": "at least 2 non-empty options are required",
        }

    clean_default = str(default).strip()

    if clean_default not in clean_options:
        return {
            "ok": False,
            "error": "default must be one of the options",
        }

    card = {
        "ok": True,
        "type": "question",
        "question": question.strip(),
        "options": clean_options,
        "default": clean_default,
        "status": "pending",
    }

    return card
