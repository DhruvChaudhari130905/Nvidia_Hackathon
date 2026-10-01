"""Pinned facts (vote results, owner overrides) that never drop out of the rolling logs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mux.agents.coordinator.conflicts import Tally

PinKind = Literal["vote", "override"]

@dataclass(frozen=True)
class Pin:
    kind: PinKind
    conflict_id : str
    text : str

def pin_vote(conflict_id: str, question: str, tally: Tally) -> Pin | None:
    if tally.winner is None:
        return None
    totals = ", ".join(f"{option} {weight}" for option, weight in tally.totals.items())
    how = "" if tally.decided_by == "votes" else f", tie broken by {tally.decided_by}"
    return Pin("vote", conflict_id, f"{question}: the team chose {tally.winner!r} ({totals}{how})")

def pin_override(conflict_id: str, question: str, option: str) -> Pin:
    return Pin("override", conflict_id, f"{question}: the owner chose {option!r}")

def merge_pins(*groups: list[Pin]) -> list[Pin]:
    """One pin per conflict: a later pin (an owner override) replaces an earlier one in its place."""
    merged: dict[str, Pin] = {}
    for group in groups:
        for pin in group:
            merged[pin.conflict_id] = pin
    return list(merged.values())

def render_pins(pins: list[Pin]) ->str:
    return "\n".join(f"- {pin.text}" for pin in pins)