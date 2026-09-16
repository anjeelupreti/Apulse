"""Throttling of repeated sign-in failures.

Counters are keyed on the identifier **as typed** and on the client IP, never on a resolved user
id. A wrong guess at an address that has no account increments the same counter as a wrong guess
at a real one, so lockout responses cannot be used to discover which accounts exist.
"""

import hashlib

from django.conf import settings
from django.core.cache import cache

_PREFIX = "auth:fail"


def _settings() -> tuple[int, int, int]:
    return (
        getattr(settings, "LOGIN_MAX_FAILED_ATTEMPTS", 5),
        getattr(settings, "LOGIN_MAX_FAILED_ATTEMPTS_PER_IP", 20),
        getattr(settings, "LOGIN_LOCKOUT_SECONDS", 900),
    )


def _key(kind: str, value: str) -> str:
    digest = hashlib.sha256(value.strip().lower().encode()).hexdigest()[:32]
    return f"{_PREFIX}:{kind}:{digest}"


def is_locked(identifier: str, ip: str) -> bool:
    per_identifier, per_ip, _ = _settings()
    if cache.get(_key("id", identifier), 0) >= per_identifier:
        return True
    return bool(ip) and cache.get(_key("ip", ip), 0) >= per_ip


def record_failure(identifier: str, ip: str) -> None:
    _, _, lockout_seconds = _settings()
    for kind, value in (("id", identifier), ("ip", ip)):
        if not value:
            continue
        key = _key(kind, value)
        try:
            cache.incr(key)
        except ValueError:  # key absent or expired
            cache.set(key, 1, timeout=lockout_seconds)


def reset(identifier: str, ip: str) -> None:
    """Clear counters after a fully successful sign-in."""
    cache.delete_many([_key("id", identifier), _key("ip", ip)])


def client_ip(request: object) -> str:
    """The client address, trusting the proxy header only where the deployment sets one."""
    meta = getattr(request, "META", {}) or {}
    if getattr(settings, "LOGIN_TRUST_FORWARDED_FOR", False):
        forwarded = str(meta.get("HTTP_X_FORWARDED_FOR", "") or "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return str(meta.get("REMOTE_ADDR", "") or "")
