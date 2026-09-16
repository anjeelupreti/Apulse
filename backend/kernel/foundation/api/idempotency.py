"""Making a retried request safe to send twice.

A counter in Birgunj presses "issue bill", the connection stalls, and the till retries. Without
this the customer is billed twice, the stock moves twice, and the numbering run gains a document
nobody meant to create. The network cannot be made reliable, so the *request* is made repeatable
instead: the client sends an `Idempotency-Key`, and a second request carrying the same key gets
the first one's answer back rather than doing the work again.

Three states, and the middle one is the one people forget:

* **unseen** — do the work, store the response against the key;
* **in flight** — the first attempt has not finished. The retry is told to wait rather than being
  allowed to run alongside it, because two concurrent bills is the exact failure being prevented;
* **finished** — replay the stored response, with a header saying so.

A key is scoped to the account, the user and the endpoint. The same key from a different user is
a different operation, and letting it replay somebody else's response would be a data leak dressed
up as a convenience.

The stored body is also checked: a client that reuses a key for a *different* payload has a bug,
and quietly returning the old answer would hide it.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import structlog
from django.core.cache import cache
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response

from shared.errors import DomainError

from . import errors

logger = structlog.get_logger(__name__)

HEADER = "Idempotency-Key"
REPLAY_HEADER = "Idempotent-Replay"

#: How long a key is remembered. A day covers a till that lost its connection overnight and
#: retried in the morning, which is the realistic worst case; beyond that the bill has been
#: chased by a person instead.
RETENTION = timedelta(hours=24)

#: How long the "in flight" marker lives if the first attempt dies without finishing. Short
#: enough that a crashed request does not block the retry for a day, long enough that a slow
#: posting is not overtaken by its own retry.
IN_FLIGHT_SECONDS = 90

_IN_FLIGHT = "__in_flight__"


@dataclass(frozen=True, slots=True)
class StoredResponse:
    status_code: int
    body: Any
    fingerprint: str
    stored_at: str


def key_from(request: Request) -> str:
    return request.headers.get(HEADER, "").strip()


def fingerprint(payload: Any) -> str:
    """A digest of what was asked for, so the same key with different content is caught."""
    try:
        canonical = json.dumps(payload, sort_keys=True, default=str)
    except (TypeError, ValueError):
        canonical = repr(payload)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def cache_key(*, tenant_id: Any, user_id: Any, path: str, key: str) -> str:
    """Scoped so one user's key can never replay another's answer."""
    scope = f"{tenant_id}:{user_id}:{path}:{key}"
    return f"idempotency:{hashlib.sha256(scope.encode()).hexdigest()}"


def replay(request: Request, *, tenant_id: Any = None, required: bool = False) -> Response | None:
    """The stored answer for this request, if there is one.

    Returns None when the work still has to be done — and marks the key as in flight before it
    does, so a retry arriving while the first attempt is mid-transaction is made to wait instead
    of billing the customer a second time.
    """
    key = key_from(request)
    if not key:
        if required:
            raise DomainError(errors.IDEMPOTENCY_KEY_REQUIRED)
        return None

    entry = cache_key(
        tenant_id=tenant_id,
        user_id=getattr(request.user, "pk", None),
        path=request.path,
        key=key,
    )
    stored = cache.get(entry)
    asked_for = fingerprint(getattr(request, "data", None))

    if stored == _IN_FLIGHT:
        raise DomainError(errors.IDEMPOTENT_REQUEST_IN_FLIGHT)

    if stored is not None:
        if stored.fingerprint != asked_for:
            # The same key for different content is a client bug. Returning the old answer would
            # hide it and look, to the person at the counter, like the bill simply did not change.
            raise DomainError(errors.IDEMPOTENCY_KEY_REUSED)
        logger.info("idempotent_replay", path=request.path, key=key)
        response = Response(stored.body, status=stored.status_code)
        response[REPLAY_HEADER] = "true"
        return response

    cache.set(entry, _IN_FLIGHT, timeout=IN_FLIGHT_SECONDS)
    return None


def remember(request: Request, response: Response, *, tenant_id: Any = None) -> None:
    """Store a finished response against its key.

    Only successful ones. A refused sale should be retryable — the counter fixes the prescription
    and presses again — and replaying the refusal would make that impossible.
    """
    key = key_from(request)
    if not key:
        return

    entry = cache_key(
        tenant_id=tenant_id,
        user_id=getattr(request.user, "pk", None),
        path=request.path,
        key=key,
    )
    if not (200 <= response.status_code < 300):
        cache.delete(entry)
        return

    cache.set(
        entry,
        StoredResponse(
            status_code=response.status_code,
            body=response.data,
            fingerprint=fingerprint(getattr(request, "data", None)),
            stored_at=timezone.now().isoformat(),
        ),
        timeout=int(RETENTION.total_seconds()),
    )


def release(request: Request, *, tenant_id: Any = None) -> None:
    """Drop the in-flight marker after a failure, so the caller may genuinely try again."""
    key = key_from(request)
    if not key:
        return
    cache.delete(
        cache_key(
            tenant_id=tenant_id,
            user_id=getattr(request.user, "pk", None),
            path=request.path,
            key=key,
        )
    )


def idempotent(required: bool = False) -> Callable[..., Any]:
    """Wrap a view method so the same key is only ever acted on once.

    ```python
    @idempotent(required=True)
    def create(self, request, *args, **kwargs): ...
    ```
    """

    def decorate(method: Callable[..., Response]) -> Callable[..., Response]:
        def wrapper(view: Any, request: Request, *args: Any, **kwargs: Any) -> Response:
            tenant_id = getattr(getattr(request, "tenant", None), "pk", None)
            stored = replay(request, tenant_id=tenant_id, required=required)
            if stored is not None:
                return stored
            try:
                response = method(view, request, *args, **kwargs)
            except Exception:
                release(request, tenant_id=tenant_id)
                raise
            remember(request, response, tenant_id=tenant_id)
            return response

        wrapper.__name__ = method.__name__
        wrapper.__doc__ = method.__doc__
        return wrapper

    return decorate
