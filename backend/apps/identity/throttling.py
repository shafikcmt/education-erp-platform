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
# M1 (review 2026-11-06): a hard lock applies only to one (email, network) pair, so attackers on
# other networks cannot lock the real user out. Globally, per email, only a capped progressive
# delay applies, which still slows distributed password guessing.


def network_subject(email_subject: str, ip: str) -> str:
    """Throttle subject for one email from one network (IPv4 /24, IPv6 /48)."""
    from apps.core.net import ip_prefix

    return crypto.blind_index(f"{email_subject}|{ip_prefix(ip) or 'unknown'}", purpose=_PURPOSE)


def _lock_key(subject: str) -> str:
    return f"lock:login:{subject}"


def _delay_key(subject: str) -> str:
    return f"delay:login:{subject}"


def _wait(key: str) -> int:
    until = cache.get(key)
    now = int(time.time())
    return int(until) - now if until is not None and int(until) > now else 0


def login_blocked_for(email_subject: str, net_subject: str) -> int:
    """Seconds until this email may try again from this network (lock or global delay)."""
    return max(_wait(_lock_key(net_subject)), _wait(_delay_key(email_subject)))


def register_login_failure(email_subject: str, net_subject: str) -> bool:
    """Record a failed login. Return ``True`` when it locks this (email, network) pair.

    * per (email, network): the 5th failure in 15 min locks that pair for 15 min;
    * per email, from any network: from the 3rd failure the next attempt waits 2, 4, 8 ...
      seconds, capped at ``SECURITY_LOGIN_MAX_DELAY_SECONDS`` (no hard lock).
    Identical for unknown emails (no enumeration).
    """
    now = int(time.time())
    global_failures = Bucket.named("login_email_failures").hit(email_subject)
    if global_failures >= 3:
        delay = min(2 ** (global_failures - 2), settings.SECURITY_LOGIN_MAX_DELAY_SECONDS)
        cache.set(_delay_key(email_subject), now + delay, timeout=delay)
    net_bucket = Bucket.named("login_email_net_failures")
    if net_bucket.hit(net_subject) >= net_bucket.limit:
        lock = settings.SECURITY_LOGIN_LOCK_SECONDS
        cache.set(_lock_key(net_subject), now + lock, timeout=lock)
        net_bucket.reset(net_subject)
        return True
    return False


def clear_login_failures(email_subject: str, net_subject: str | None = None) -> None:
    Bucket.named("login_email_failures").reset(email_subject)
    cache.delete(_delay_key(email_subject))
    if net_subject is not None:
        Bucket.named("login_email_net_failures").reset(net_subject)


# ------------------------------------------------------------------ per-account MFA lock (H1)
# Counted per USER, not per session, so signing in again with the password never resets it.


def _mfa_subject(user_id: object) -> str:
    return crypto.blind_index(f"mfa:{user_id}", purpose=_PURPOSE)


def mfa_blocked_for(user_id: object) -> int:
    return _wait(f"lock:mfa:{_mfa_subject(user_id)}")


def register_mfa_failure(user_id: object) -> bool:
    """Count a failed TOTP/recovery code (login or step-up). ``True`` when it locks MFA."""
    subject = _mfa_subject(user_id)
    bucket = Bucket.named("mfa_user_failures")
    if bucket.hit(subject) >= bucket.limit:
        lock = settings.SECURITY_MFA_LOCK_SECONDS
        cache.set(f"lock:mfa:{subject}", int(time.time()) + lock, timeout=lock)
        bucket.reset(subject)
        return True
    return False


def clear_mfa_lock(user_id: object) -> None:
    """Used by an administrator's MFA reset (the recovery path besides waiting)."""
    subject = _mfa_subject(user_id)
    Bucket.named("mfa_user_failures").reset(subject)
    cache.delete(f"lock:mfa:{subject}")
