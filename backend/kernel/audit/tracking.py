"""Logging every change to a model, without every service having to remember to.

The audit trail was there from the start, but only where somebody wrote a call to it. That is the
wrong way round: the entries that matter most are the ones nobody thought to add, because the
person changing a price quietly at midnight is not the person who wrote the logging call.

So a model is *declared* as tracked, once, next to the app it belongs to, and every create, change
and delete of it is recorded from then on. A service that wants to say something better — "invoice
INV-001 issued, 1,240.00" rather than "status: draft → issued" — records that itself and wraps the
save in `paused()` so the row-level entry does not repeat it.

**What is deliberately not tracked**

* the stock ledger and the narcotic register — they *are* logs, append-only in the database, and
  auditing a log produces two copies of the same fact;
* stock balances — a running total derived from the ledger, not a record of anything;
* the audit trail itself, which would be a loop.

**What this costs.** Each tenant's trail is a hash chain, so appending takes a lock on that
tenant's chain head and entries for one tenant are written one at a time. That is the price of a
chain that can be verified, and it is why master data and documents are tracked while the ledger,
which is written on every scan at the counter, is not.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import structlog
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save

from kernel.tenancy.context import get_current_tenant_id

logger = structlog.get_logger(__name__)

#: Fields whose change is not news. `updated_at` moves on every save, so without excluding it no
#: diff would ever come out empty and every touch would look like a change.
ALWAYS_IGNORED = frozenset({"id", "created_at", "updated_at", "tenant"})

_BEFORE = "_audit_snapshot_before"

_paused: ContextVar[bool] = ContextVar("audit_tracking_paused", default=False)


@dataclass(frozen=True, slots=True)
class Tracked:
    model: type[models.Model]
    ignore: frozenset[str] = field(default_factory=frozenset)

    @property
    def label(self) -> str:
        return self.model._meta.label


_registry: dict[str, Tracked] = {}


def track(model: type[models.Model], *, ignore: tuple[str, ...] = ()) -> type[models.Model]:
    """Record every create, change and delete of this model from now on.

    Called from an app's `ready()`, next to the model it covers, so that adding a model and
    forgetting to log it is a visible omission in one file rather than an invisible one spread
    across a service layer.
    """
    entry = Tracked(model=model, ignore=frozenset(ignore) | ALWAYS_IGNORED)
    label = entry.label
    if label in _registry:
        return model

    _registry[label] = entry
    dispatch_uid = f"audit_tracking:{label}"
    pre_save.connect(_remember_before, sender=model, dispatch_uid=dispatch_uid)
    post_save.connect(_record_save, sender=model, dispatch_uid=dispatch_uid)
    post_delete.connect(_record_delete, sender=model, dispatch_uid=dispatch_uid)
    return model


def is_tracked(model: type[models.Model]) -> bool:
    return model._meta.label in _registry


def tracked_models() -> tuple[str, ...]:
    return tuple(sorted(_registry))


@contextmanager
def paused() -> Iterator[None]:
    """Stop row-level tracking for this block.

    For a save a service is already recording in better words. Not a way to make a change
    invisible: the service is expected to record its own entry instead, and a block that both
    pauses tracking and records nothing is a bug, not a feature.
    """
    token = _paused.set(True)
    try:
        yield
    finally:
        _paused.reset(token)


# --------------------------------------------------------------------------- the signal handlers
def _should_record(raw: bool) -> bool:
    if raw or _paused.get():
        return False
    # The trail is per tenant. A change made with no tenant bound — a migration, a management
    # command touching platform data — has no chain to go on. The control plane keeps its own.
    return get_current_tenant_id() is not None


def _remember_before(sender: type[models.Model], instance: models.Model, **kwargs: Any) -> None:
    """Read the row as it is now, so the change can be described as a before and after."""
    if kwargs.get("raw") or _paused.get() or instance.pk is None:
        return
    previous = sender._base_manager.filter(pk=instance.pk).first()
    setattr(instance, _BEFORE, _comparable(previous) if previous is not None else None)


def _record_save(
    sender: type[models.Model], instance: models.Model, created: bool, **kwargs: Any
) -> None:
    from .models import AuditAction
    from .services import record

    if not _should_record(bool(kwargs.get("raw"))):
        return

    entry = _registry[sender._meta.label]
    before = getattr(instance, _BEFORE, None)

    if created or before is None:
        changes = {name: {"from": None, "to": value} for name, value in _snapshot(instance).items()}
        action = AuditAction.CREATE
    else:
        changes = _diff(before, _comparable(instance), ignore=entry.ignore)
        action = AuditAction.UPDATE
        if not changes:
            return  # a save that changed nothing is not a change

    record(action=action, entity=instance, changes=changes)


def _record_delete(
    sender: type[models.Model],  # noqa: ARG001 — required by the signal contract
    instance: models.Model,
    **kwargs: Any,
) -> None:
    from .models import AuditAction
    from .services import record

    if not _should_record(bool(kwargs.get("raw"))):
        return

    record(
        action=AuditAction.DELETE,
        entity=instance,
        changes={name: {"from": value, "to": None} for name, value in _snapshot(instance).items()},
    )


def _snapshot(instance: models.Model) -> dict[str, Any]:
    from .diffing import snapshot

    return snapshot(instance)


def _comparable(instance: models.Model) -> dict[str, Any]:
    from .diffing import comparable

    return comparable(instance)


def _diff(
    before: dict[str, Any], after: dict[str, Any], *, ignore: frozenset[str]
) -> dict[str, dict[str, Any]]:
    from .diffing import diff

    return {name: change for name, change in diff(before, after).items() if name not in ignore}
