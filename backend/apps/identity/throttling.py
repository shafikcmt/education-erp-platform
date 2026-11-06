"""Brute-force protection with cache counters (Redis in dev/prod; plan §6.2).

Keys never contain a plaintext IP or email: they use the ADR-036 keyed HMAC. Windows are fixed
(``cache.add`` + ``cache.incr``), which is atomic on Redis. No new dependency.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from apps.core import crypto

_PURPOSE = "security.throttle"


def subject_key(kind: str, value: str) -> str:
    """HMAC of a throttle subject (``kind`` is e.g. ``"ip"`` or ``"email"``)."""
    return crypto.blind_index(f"{kind}:{value.strip().lower()}", purpose=_PURPOSE)


@dataclass(frozen=True)
class Bucket:
    name: str
    limit: int
    window: int

    @classmethod
    def named(cls, name: str) -> Bucket:
        limit, window = settings.SECURITY_THROTTLES[name]
        return cls(name, limit, window)

    def _key(self, subject: str) -> str:
        return f"thr:{self.name}:{subject}"

    def hit(self, subject: str) -> int:
        """Count one event; return the count within the current window."""
        key = self._key(subject)
        cache.add(key, 0, timeout=self.window)
        cache.add(f"{key}:start", int(time.time()), timeout=self.window)
        try:
            return int(cache.incr(key))
        except ValueError:  # expired between add and incr
            cache.set(key, 1, timeout=self.window)
            return 1

    def count(self, subject: str) -> int:
        return int(cache.get(self._key(subject), 0))

    def exceeded(self, subject: str) -> bool:
        return self.count(subject) >= self.limit

    def retry_after(self, subject: str) -> int:
        start = cache.get(f"{self._key(subject)}:start")
        if start is None:
            return self.window
        return max(1, int(start) + self.window - int(time.time()))

    def reset(self, subject: str) -> None:
        cache.delete_many([self._key(subject), f"{self._key(subject)}:start"])


# ------------------------------------------------------------------ login lock + progressive delay
def _lock_key(subject: str) -> str:
    return f"lock:login:{subject}"


def _delay_key(subject: str) -> str:
    return f"delay:login:{subject}"


def login_blocked_for(subject: str) -> int:
    """Seconds until the email subject may try again (lock or progressive delay), else 0."""
    now = int(time.time())
    for key in (_lock_key(subject), _delay_key(subject)):
        until = cache.get(key)
        if until is not None and int(until) > now:
            return int(until) - now
    return 0


def register_login_failure(subject: str) -> bool:
    """Record a failed login for an email subject. Return ``True`` when it triggers a lock.

    From the 3rd failure the next attempt must wait 2, 4, ... seconds; the 5th failure in 15 min
    locks the subject for ``SECURITY_LOGIN_LOCK_SECONDS``. Identical for unknown emails.
    """
    bucket = Bucket.named("login_email_failures")
    failures = bucket.hit(subject)
    now = int(time.time())
    if failures >= bucket.limit:
        lock = settings.SECURITY_LOGIN_LOCK_SECONDS
        cache.set(_lock_key(subject), now + lock, timeout=lock)
        bucket.reset(subject)
        return True
    if failures >= 3:
        delay = 2 ** (failures - 2)
        cache.set(_delay_key(subject), now + delay, timeout=delay)
    return False


def clear_login_failures(subject: str) -> None:
    Bucket.named("login_email_failures").reset(subject)
    cache.delete_many([_delay_key(subject)])
