"""Durable event log: each room's events as JSON lines in <root>/<room_id>.jsonl.

Rooms rebuild from their events after a restart (registry.get_room_or_rehydrate), so keeping the events
on disk is enough to keep rooms. Reads are served from memory; the file is loaded once and appended to.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

from mux.events import models
from mux.events.log import InMemoryEventLog
from mux.events.models import BaseEvent

logger = logging.getLogger(__name__)


def _encode(event: BaseEvent) -> str:
    # The class name is stored too: several event types share a model, and replay casts by model
    return json.dumps({"cls": type(event).__name__, "event": event.model_dump(mode="json")}, separators=(",", ":"))


def _decode(line: str) -> BaseEvent:
    record: dict[str, Any] = json.loads(line)
    cls = getattr(models, record["cls"], None)
    if not (isinstance(cls, type) and issubclass(cls, BaseEvent)):
        raise ValueError(f"unknown event class {record['cls']!r}")
    return cls.model_validate(record["event"])


class FileEventLog(InMemoryEventLog):
    """InMemoryEventLog that also appends every event to disk and loads them back on creation."""

    def __init__(self, room_id: str, root: Path) -> None:
        super().__init__(room_id)
        self._path = root / f"{room_id}.jsonl"
        if self._path.exists():
            self._load()

    def _load(self) -> None:
        with self._path.open(encoding="utf-8") as f:
            for number, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    event = _decode(line)
                except (ValueError, KeyError) as e:
                    # A half-written last line (crash mid-append) is dropped; anything else is a real problem
                    logger.error(f"{self._path}:{number}: skipping unreadable event: {e}")
                    continue
                self._events.append(event)
                self._sequence = event.sequence
                if event.type == models.EventType.CHECKPOINT_CREATED:
                    self._checkpoints.append(cast(models.CheckpointCreatedEvent, event))

    async def append(self, event: BaseEvent) -> None:
        await super().append(event)  # assigns the sequence
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(_encode(event) + "\n")


def events_root() -> Path:
    """Where room events are kept (next to the room files, under the server's working directory)."""
    return Path.cwd() / ".mux" / "events"


def stored_room_ids(root: Path | None = None) -> list[str]:
    """Ids of the rooms that have events on disk."""
    root = root or events_root()
    return sorted(p.stem for p in root.glob("*.jsonl")) if root.is_dir() else []
