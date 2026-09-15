"""Registry of every error code the API may return (see docs/CONVENTIONS.md §4.5)."""

import re
from dataclasses import dataclass

_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class ErrorCode:
    code: str
    http_status: int
    message_en: str
    message_ne: str


_registry: dict[str, ErrorCode] = {}


def register(code: str, http_status: int, message_en: str, message_ne: str) -> ErrorCode:
    """Register an error code. Codes are global, so duplicates are a programming error."""
    if not _CODE_PATTERN.fullmatch(code):
        raise ValueError(f"Error code must be UPPER_SNAKE_CASE: {code!r}")
    if not 400 <= http_status <= 599:
        raise ValueError(f"HTTP status for {code} must be 4xx or 5xx, got {http_status}")
    if not message_en.strip() or not message_ne.strip():
        raise ValueError(f"Error code {code} needs both English and Nepali messages")
    if code in _registry:
        raise ValueError(f"Error code already registered: {code}")
    error = ErrorCode(code, http_status, message_en, message_ne)
    _registry[code] = error
    return error


def get(code: str) -> ErrorCode:
    try:
        return _registry[code]
    except KeyError:
        raise LookupError(f"Unregistered error code: {code}") from None


def all_codes() -> tuple[ErrorCode, ...]:
    return tuple(_registry.values())
