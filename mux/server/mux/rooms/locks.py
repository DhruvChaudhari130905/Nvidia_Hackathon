"""Soft locks for manual editing: one person edits a file at a time, others see it read-only."""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, replace
from typing import Callable, Dict, Optional, Tuple, ContextManager, AsyncContextManager


@dataclass(frozen=True, slots=True)
class LockInfo:
    """Information about a file lock (immutable)."""
    user_id: str
    acquired_at: float  # time.monotonic()

    def is_idle(self, idle_seconds: int) -> bool:
        """Return True if the lock has been idle longer than idle_seconds."""
        return (time.monotonic() - self.acquired_at) > idle_seconds

    def age_seconds(self) -> float:
        """Return how many seconds this lock has been held."""
        return time.monotonic() - self.acquired_at

    def refresh(self) -> "LockInfo":
        """Return a new LockInfo with updated timestamp."""
        return replace(self, acquired_at=time.monotonic())

    def __repr__(self) -> str:
        return f"LockInfo(user_id={self.user_id!r}, acquired_at={self.acquired_at:.2f})"


@dataclass(frozen=True, slots=True)
class IdleLocks:
    """Result of get_idle_locks()."""
    locked_paths: Tuple[str, ...]
    idle_locked_paths: Tuple[str, ...]


# Callback type for lock expiration notification
LockExpiryCallback = Callable[[str, str], None]  # (path, user_id) -> None


class LockManager:
    """Manager for soft file locks."""

    def __init__(
        self,
        idle_timeout: int = 120,
        *,
        use_asyncio: bool = True,
        on_lock_expire: Optional[LockExpiryCallback] = None,
    ) -> None:
        """Initialize the lock manager.
        Args:
            idle_timeout: Number of seconds after which a lock is considered idle (default 2 minutes).
            use_asyncio: If True, use asyncio.Lock for async safety. If False, use threading.RLock for thread safety.
            on_lock_expire: Optional callback fired when a lock is auto-released due to idleness.
                Receives (path, user_id). Called from release_idle_locks() *without* the lock held.
                If use_asyncio=False, callback must be thread-safe (called from sync context).
        """
        self._locks: Dict[str, LockInfo] = {}
        self._idle_timeout = idle_timeout
        self._use_asyncio = use_asyncio
        self._async_mutex: Optional[asyncio.Lock] = asyncio.Lock() if use_asyncio else None
        self._sync_mutex: Optional[threading.RLock] = threading.RLock() if not use_asyncio else None
        self._on_lock_expire = on_lock_expire
        # Nesting counters for reentrant context managers: (path, user_id) -> count
        self._nesting: Dict[Tuple[str, str], int] = {}

    def _get_mutex(self) -> asyncio.Lock | threading.RLock:
        """Get the appropriate mutex for the current mode."""
        if self._use_asyncio:
            assert self._async_mutex is not None
            return self._async_mutex
        assert self._sync_mutex is not None
        return self._sync_mutex

    async def lock(self, path: str, user_id: str) -> bool:
        """Attempt to take a lock on the given path for the given user.
        Returns True if the lock was acquired, False if already locked by another user.
        If the same user already holds the lock, refreshes the timestamp and returns True.
        """
        mutex = self._get_mutex()
        async with mutex:
            existing = self._locks.get(path)
            if existing is None:
                # No lock, take it
                self._locks[path] = LockInfo(user_id, time.monotonic())
                return True
            if existing.user_id == user_id:
                # Same user, refresh the lock
                self._locks[path] = existing.refresh()
                return True
            # Locked by another user
            return False

    def lock_sync(self, path: str, user_id: str) -> bool:
        """Synchronous version of lock() for thread-based usage."""
        mutex = self._get_mutex()
        with mutex:
            existing = self._locks.get(path)
            if existing is None:
                self._locks[path] = LockInfo(user_id, time.monotonic())
                return True
            if existing.user_id == user_id:
                self._locks[path] = existing.refresh()
                return True
            return False

    async def unlock(self, path: str, user_id: str) -> bool:
        """Release the lock on the given path if held by the given user.
        Returns True if the lock was released, False if the lock is not held by that user.
        """
        mutex = self._get_mutex()
        async with mutex:
            existing = self._locks.get(path)
            if existing is None:
                return False
            if existing.user_id != user_id:
                return False
            del self._locks[path]
            return True

    def unlock_sync(self, path: str, user_id: str) -> bool:
        """Synchronous version of unlock() for thread-based usage."""
        mutex = self._get_mutex()
        with mutex:
            existing = self._locks.get(path)
            if existing is None:
                return False
            if existing.user_id != user_id:
                return False
            del self._locks[path]
            return True

    async def is_locked(self, path: str) -> bool:
        """Return True if the path is currently locked by any user."""
        mutex = self._get_mutex()
        async with mutex:
            return path in self._locks

    def is_locked_sync(self, path: str) -> bool:
        mutex = self._get_mutex()
        with mutex:
            return path in self._locks

    async def locked_by(self, path: str) -> Optional[str]:
        """Return the user ID holding the lock on the path, or None if not locked."""
        mutex = self._get_mutex()
        async with mutex:
            lock_info = self._locks.get(path)
            return lock_info.user_id if lock_info else None

    def locked_by_sync(self, path: str) -> Optional[str]:
        mutex = self._get_mutex()
        with mutex:
            lock_info = self._locks.get(path)
            return lock_info.user_id if lock_info else None

    async def refresh_lock(self, path: str, user_id: str) -> bool:
        """Refresh the lock timestamp for the given path and user.
        Returns True if the lock exists and is held by the given user, False otherwise.
        """
        mutex = self._get_mutex()
        async with mutex:
            existing = self._locks.get(path)
            if existing is None or existing.user_id != user_id:
                return False
            self._locks[path] = existing.refresh()
            return True

    def refresh_lock_sync(self, path: str, user_id: str) -> bool:
        mutex = self._get_mutex()
        with mutex:
            existing = self._locks.get(path)
            if existing is None or existing.user_id != user_id:
                return False
            self._locks[path] = existing.refresh()
            return True

    async def get_lock_age(self, path: str) -> Optional[float]:
        """Return how many seconds the lock has been held, or None if not locked."""
        mutex = self._get_mutex()
        async with mutex:
            lock_info = self._locks.get(path)
            return lock_info.age_seconds() if lock_info else None

    def get_lock_age_sync(self, path: str) -> Optional[float]:
        mutex = self._get_mutex()
        with mutex:
            lock_info = self._locks.get(path)
            return lock_info.age_seconds() if lock_info else None

    async def get_idle_locks(self) -> IdleLocks:
        """Return IdleLocks with locked_paths and idle_locked_paths."""
        mutex = self._get_mutex()
        async with mutex:
            locked_paths = tuple(self._locks.keys())
            idle_locked_paths = tuple(
                path for path, lock_info in self._locks.items() if lock_info.is_idle(self._idle_timeout)
            )
            return IdleLocks(locked_paths, idle_locked_paths)

    def get_idle_locks_sync(self) -> IdleLocks:
        mutex = self._get_mutex()
        with mutex:
            locked_paths = tuple(self._locks.keys())
            idle_locked_paths = tuple(
                path for path, lock_info in self._locks.items() if lock_info.is_idle(self._idle_timeout)
            )
            return IdleLocks(locked_paths, idle_locked_paths)

    async def get_all_locks(self) -> dict[str, LockInfo]:
        """Return all currently held locks as a dict of path -> LockInfo."""
        mutex = self._get_mutex()
        async with mutex:
            return dict(self._locks)

    async def release_idle_locks(self) -> list[str]:
        """Release all locks that have been idle longer than the idle timeout.
        Returns the list of paths that were unlocked.
        """
        mutex = self._get_mutex()
        expired: list[tuple[str, str]] = []
        async with mutex:
            for path, lock_info in list(self._locks.items()):
                if lock_info.is_idle(self._idle_timeout):
                    expired.append((path, lock_info.user_id))
            for path, user_id in expired:
                del self._locks[path]
        for path, user_id in expired:
            if self._on_lock_expire:
                self._on_lock_expire(path, user_id)
        return [path for path, _ in expired]

    def release_idle_locks_sync(self) -> list[str]:
        mutex = self._get_mutex()
        expired: list[tuple[str, str]] = []
        with mutex:
            for path, lock_info in list(self._locks.items()):
                if lock_info.is_idle(self._idle_timeout):
                    expired.append((path, lock_info.user_id))
            for path, user_id in expired:
                del self._locks[path]
        for path, user_id in expired:
            if self._on_lock_expire:
                self._on_lock_expire(path, user_id)
        return [path for path, _ in expired]

    # Context managers for ergonomic lock/unlock
    @asynccontextmanager
    async def locked(self, path: str, user_id: str) -> AsyncContextManager[None]:
        """Async context manager: acquire lock on enter, release on exit.
        Reentrant: same user can nest contexts; lock released on outermost exit.
        Raises RuntimeError if lock cannot be acquired (held by another user).
        Usage:
            async with manager.locked("file.py", "user123"):
                # edit file
                ...
            # lock auto-released
        """
        mutex = self._get_mutex()
        key = (path, user_id)
        acquired = False
        async with mutex:
            existing = self._locks.get(path)
            if existing is None:
                self._locks[path] = LockInfo(user_id, time.monotonic())
                acquired = True
            elif existing.user_id == user_id:
                self._locks[path] = existing.refresh()
                acquired = True
        if not acquired:
            raise RuntimeError(f"Could not acquire lock on {path!r}")

        # Increment nesting counter
        async with mutex:
            self._nesting[key] = self._nesting.get(key, 0) + 1

        try:
            yield
        finally:
            # Decrement nesting counter; only release on outermost exit
            async with mutex:
                count = self._nesting.get(key, 0)
                if count <= 1:
                    self._nesting.pop(key, None)
                    existing = self._locks.get(path)
                    if existing and existing.user_id == user_id:
                        del self._locks[path]
                else:
                    self._nesting[key] = count - 1

    @contextmanager
    def locked_sync(self, path: str, user_id: str) -> ContextManager[None]:
        """Sync context manager: acquire lock on enter, release on exit.
        Reentrant: same user can nest contexts; lock released on outermost exit.
        Raises RuntimeError if lock cannot be acquired (held by another user).
        """
        mutex = self._get_mutex()
        key = (path, user_id)
        acquired = False
        with mutex:
            existing = self._locks.get(path)
            if existing is None:
                self._locks[path] = LockInfo(user_id, time.monotonic())
                acquired = True
            elif existing.user_id == user_id:
                self._locks[path] = existing.refresh()
                acquired = True
        if not acquired:
            raise RuntimeError(f"Could not acquire lock on {path!r}")

        # Increment nesting counter
        with mutex:
            self._nesting[key] = self._nesting.get(key, 0) + 1

        try:
            yield
        finally:
            # Decrement nesting counter; only release on outermost exit
            with mutex:
                count = self._nesting.get(key, 0)
                if count <= 1:
                    self._nesting.pop(key, None)
                    existing = self._locks.get(path)
                    if existing and existing.user_id == user_id:
                        del self._locks[path]
                else:
                    self._nesting[key] = count - 1

    # Lock transfer
    async def transfer_lock(self, path: str, from_user: str, to_user: str) -> bool:
        """Transfer lock ownership from one user to another.
        Preserves original acquisition timestamp.
        Returns True if transfer succeeded, False if lock not held by from_user.
        """
        mutex = self._get_mutex()
        async with mutex:
            existing = self._locks.get(path)
            if existing is None or existing.user_id != from_user:
                return False
            self._locks[path] = LockInfo(to_user, existing.acquired_at)
            return True

    def transfer_lock_sync(self, path: str, from_user: str, to_user: str) -> bool:
        mutex = self._get_mutex()
        with mutex:
            existing = self._locks.get(path)
            if existing is None or existing.user_id != from_user:
                return False
            self._locks[path] = LockInfo(to_user, existing.acquired_at)
            return True

    # Get all locks (for admin/debug)
    async def get_all_locks(self) -> Dict[str, LockInfo]:
        """Return a copy of all current locks: path -> LockInfo."""
        mutex = self._get_mutex()
        async with mutex:
            return dict(self._locks)

    def get_all_locks_sync(self) -> Dict[str, LockInfo]:
        mutex = self._get_mutex()
        with mutex:
            return dict(self._locks)

    async def get_lock(self, path: str) -> Optional[LockInfo]:
        """Get lock info for a specific path."""
        mutex = self._get_mutex()
        async with mutex:
            return self._locks.get(path)

    def get_lock_sync(self, path: str) -> Optional[LockInfo]:
        """Synchronous version of get_lock."""
        mutex = self._get_mutex()
        with mutex:
            return self._locks.get(path)

    def __repr__(self) -> str:
        mode = "async" if self._use_asyncio else "sync"
        return f"LockManager(idle_timeout={self._idle_timeout}, mode={mode}, locks={len(self._locks)})"

    def __len__(self) -> int:
        """Return lock count. (An asyncio.Lock can't be used with a plain `with`,
        so in async mode this reads without the mutex; dict reads are atomic.)"""
        if self._use_asyncio:
            return len(self._locks)
        with self._get_mutex():
            return len(self._locks)

    def __contains__(self, path: str) -> bool:
        """Return True if path is locked."""
        if self._use_asyncio:
            return path in self._locks
        with self._get_mutex():
            return path in self._locks