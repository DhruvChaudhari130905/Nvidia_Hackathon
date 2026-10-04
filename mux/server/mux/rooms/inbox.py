"""Pending messages waiting for the coder. Drained at each turn boundary (merges injected, interrupts abort)."""

from __future__ import annotations

import asyncio
import time
from typing import TypedDict, Optional, Literal, List


class InboxMessage(TypedDict, total=False):
    """Type-safe inbox message schema."""
    label: Literal["merge", "queue", "interrupt", "conflict", "chat"]
    content: str
    message_id: Optional[str]
    user_id: Optional[str]
    rationale: Optional[str]
    domain: Optional[str]
    timestamp: float


VALID_LABELS = frozenset({"merge", "queue", "interrupt", "conflict", "chat"})


class Inbox:
    """Inbox of messages waiting for the coder to process at turn boundaries.

    Async-safe with internal lock. Unbounded by default; set max_size for backpressure.
    """

    def __init__(self, max_size: int = 0) -> None:
        """
        Args:
            max_size: Maximum messages before add() raises. 0 = unbounded.
        """
        self._messages: List[InboxMessage] = []
        self._lock = asyncio.Lock()
        self._max_size = max_size

    async def add(
        self,
        label: str,
        content: str,
        *,
        message_id: Optional[str] = None,
        user_id: Optional[str] = None,
        rationale: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> None:
        """Add a labeled message to the inbox.

        Args:
            label: The coordinator's label (merge, queue, interrupt, conflict, chat).
            content: The message text.
            message_id: Unique identifier of the message.
            user_id: ID of the user who sent the message.
            rationale: Coordinator's rationale for the label.
            domain: User domain role (ui, architecture, scope, or None).

        Raises:
            ValueError: If label invalid or inbox full (max_size exceeded).
        """
        if label not in VALID_LABELS:
            raise ValueError(f"Invalid label '{label}'. Must be one of {sorted(VALID_LABELS)}")

        async with self._lock:
            if self._max_size and len(self._messages) >= self._max_size:
                raise ValueError(f"Inbox full (max_size={self._max_size})")

            self._messages.append(
                InboxMessage(
                    label=label,
                    content=content,
                    message_id=message_id,
                    user_id=user_id,
                    rationale=rationale,
                    domain=domain,
                    timestamp=time.time(),
                )
            )

    async def drain(self) -> tuple[List[str], List[str], bool]:
        """Process and clear the inbox at a turn boundary.

        Returns:
            merges: List of message contents labeled "merge" to inject into the coder's context.
            edit_notes: List of manual edit notes (not implemented; manual edits via locks).
            interrupt: True if any message labeled "interrupt" is present, causing the coder to abort and re-plan.
        """
        async with self._lock:
            # Snapshot messages to process (don't clear yet - only clear on successful processing)
            messages = self._messages[:]

        merges: List[str] = []
        edit_notes: List[str] = []  # Manual edits are handled via locks and passed separately.
        interrupt = False

        for msg in messages:
            if msg["label"] == "merge":
                merges.append(msg["content"])
            elif msg["label"] == "interrupt":
                interrupt = True
            # Other labels (queue, conflict, chat) are not processed by the coder at turn boundaries.

        # Only clear the inbox after successful processing
        async with self._lock:
            # Verify messages haven't been modified during processing
            # (in practice, new messages may have been added - only remove the ones we processed)
            if len(self._messages) >= len(messages):
                # Remove the processed messages from the front
                self._messages = self._messages[len(messages):]
            else:
                # Inbox was modified unexpectedly, clear what we can
                self._messages.clear()

        return merges, edit_notes, interrupt

    async def peek(self) -> List[InboxMessage]:
        """Return a copy of all messages without clearing."""
        async with self._lock:
            return [msg.copy() for msg in self._messages]

    async def clear(self) -> int:
        """Clear all messages. Returns count of removed messages."""
        async with self._lock:
            count = len(self._messages)
            self._messages.clear()
            return count

    def __len__(self) -> int:
        # Sync peek for debugging; not async-safe for concurrent use
        return len(self._messages)

    async def __len_async__(self) -> int:
        """Async-safe length."""
        async with self._lock:
            return len(self._messages)