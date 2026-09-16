"""Field and key names whose values must never be written to logs or audit records."""

from typing import Any

MASK = "***"

SENSITIVE_NAMES = frozenset(
    {
        "password",
        "password1",
        "password2",
        "new_password",
        "old_password",
        "secret",
        "token",
        "access",
        "refresh",
        "authorization",
        "api_key",
        "private_key",
        "otp",
        "pin",
        "code_hash",
        "challenge_token",
        "verification_token",
        "session_key",
    }
)


def is_sensitive(name: str) -> bool:
    return name.lower() in SENSITIVE_NAMES


def redact(name: str, value: Any) -> Any:
    """Return the value, or a mask if the name says it is a secret."""
    return MASK if is_sensitive(name) else value
