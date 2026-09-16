"""Who and where an audited action came from.

Services deep in the call stack should not have to be handed the request, so the caller's details
are put in a context variable at the edge and read from there.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditContext:
    request_id: str = ""
    ip_address: str = ""
    user_agent: str = ""
    device_id: str = ""
    #: Who is acting. Kept here so a service deep in the stack, or a signal handler that was never
    #: passed anything, still records a name rather than an anonymous change.
    actor: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        data = {
            "request_id": self.request_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "device_id": self.device_id,
            **self.extra,
        }
        return {key: value for key, value in data.items() if value}


_EMPTY = AuditContext()
_current: ContextVar[AuditContext] = ContextVar("audit_context", default=_EMPTY)


def get_context() -> AuditContext:
    return _current.get()


def set_context(context: AuditContext) -> object:
    return _current.set(context)


def reset_context(token: object) -> None:
    _current.reset(token)  # type: ignore[arg-type]


@contextmanager
def audit_context(**values: Any) -> Iterator[AuditContext]:
    """Temporarily describe the caller, for background jobs and management commands."""
    known = {"request_id", "ip_address", "user_agent", "device_id", "actor"}
    context = AuditContext(
        **{key: value for key, value in values.items() if key in known},
        extra={key: value for key, value in values.items() if key not in known},
    )
    token = _current.set(context)
    try:
        yield context
    finally:
        _current.reset(token)
