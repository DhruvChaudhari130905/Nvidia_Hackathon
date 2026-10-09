"""Room passwords: salted scrypt hashes, and a per-user limit on wrong guesses."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

# scrypt cost (2**14 * 8 * 128 bytes = 16 MB per hash), stored in the hash so it can change later
_N, _R, _P = 2**14, 8, 1

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300


def hash_password(password: str) -> str:
    """'scrypt$n$r$p$salt$hash', both base64."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return "$".join(["scrypt", str(_N), str(_R), str(_P), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()])


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


class AttemptLimiter:
    """Counts wrong passwords per (room, user); MAX_FAILED_ATTEMPTS within LOCKOUT_SECONDS locks that pair out.

    In memory: a restart clears it, which is fine for slowing down guessing.
    """

    def __init__(self, max_failures: int = MAX_FAILED_ATTEMPTS, window: float = LOCKOUT_SECONDS) -> None:
        self.max_failures = max_failures
        self.window = window
        self._failures: dict[tuple[str, str], list[float]] = {}

    def _recent(self, key: tuple[str, str]) -> list[float]:
        cutoff = time.monotonic() - self.window
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def retry_after(self, room_id: str, user_id: str) -> float:
        """Seconds until this user may guess again; 0 when they may now."""
        recent = self._recent((room_id, user_id))
        if len(recent) < self.max_failures:
            return 0.0
        return max(0.0, recent[0] + self.window - time.monotonic())

    def record_failure(self, room_id: str, user_id: str) -> None:
        key = (room_id, user_id)
        self._failures[key] = self._recent(key) + [time.monotonic()]

    def reset(self, room_id: str, user_id: str) -> None:
        self._failures.pop((room_id, user_id), None)


password_attempts = AttemptLimiter()
