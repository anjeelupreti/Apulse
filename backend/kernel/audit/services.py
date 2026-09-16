"""Appending to the audit trail, and checking that nobody has tampered with it."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, cast

import structlog
from django.db import models, transaction

from kernel.tenancy.context import require_current_tenant_id

from .context import get_context
from .diffing import diff, snapshot
from .models import GENESIS_HASH, AuditAction, AuditChainHead, AuditEvent

logger = structlog.get_logger(__name__)


def compute_hash(*, previous_hash: str, payload: dict[str, Any]) -> str:
    """SHA-256 over the previous hash and this entry's meaningful fields.

    Canonical JSON (sorted keys) so the same entry always hashes the same way, whatever order the
    dictionary happened to be built in.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{previous_hash}{canonical}".encode()).hexdigest()


def _payload(
    *,
    sequence: int,
    action: str,
    actor_id: Any,
    entity_type: str,
    entity_id: str,
    changes: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "action": action,
        "actor_id": str(actor_id) if actor_id else None,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "changes": changes,
        "reason": reason,
    }


@transaction.atomic
def record(
    *,
    action: str,
    actor: Any = None,
    entity: models.Model | None = None,
    entity_type: str = "",
    entity_id: str = "",
    entity_label: str = "",
    changes: dict[str, Any] | None = None,
    reason: str = "",
    branch: Any = None,
) -> AuditEvent:
    """Append one entry to the current tenant's chain.

    The chain head is locked for the duration, so concurrent writers cannot produce two entries
    claiming the same position or both pointing at the same predecessor.
    """
    tenant_id = require_current_tenant_id()

    if entity is not None:
        entity_type = entity_type or entity._meta.label
        entity_id = entity_id or str(entity.pk)
        entity_label = entity_label or str(entity)[:300]

    AuditChainHead.all_tenants.get_or_create(
        tenant_id=tenant_id, defaults={"sequence": 0, "last_hash": GENESIS_HASH}
    )
    head = cast(
        "AuditChainHead",
        AuditChainHead.all_tenants.select_for_update().get(tenant_id=tenant_id),
    )

    sequence = head.sequence + 1
    changes = changes or {}
    actor_id = getattr(actor, "pk", None)
    digest = compute_hash(
        previous_hash=head.last_hash,
        payload=_payload(
            sequence=sequence,
            action=action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            reason=reason,
        ),
    )

    event = cast(
        "AuditEvent",
        AuditEvent.all_tenants.create(
            tenant_id=tenant_id,
            sequence=sequence,
            previous_hash=head.last_hash,
            hash=digest,
            action=action,
            actor=actor if actor_id else None,
            actor_label=str(actor)[:200] if actor is not None else "",
            entity_type=entity_type,
            entity_id=entity_id,
            entity_label=entity_label,
            branch=branch,
            changes=changes,
            context=get_context().as_dict(),
            reason=reason,
        ),
    )

    head.sequence = sequence
    head.last_hash = digest
    head.save(update_fields=["sequence", "last_hash", "updated_at"])
    return event


def record_create(instance: models.Model, *, actor: Any = None, reason: str = "") -> AuditEvent:
    return record(
        action=AuditAction.CREATE,
        actor=actor,
        entity=instance,
        changes={name: {"from": None, "to": value} for name, value in snapshot(instance).items()},
        reason=reason,
    )


def record_update(
    instance: models.Model,
    before: dict[str, Any],
    *,
    actor: Any = None,
    reason: str = "",
    action: str = AuditAction.UPDATE,
) -> AuditEvent | None:
    """Record a change, or nothing at all if the save changed nothing."""
    changes = diff(before, snapshot(instance))
    if not changes:
        return None
    return record(action=action, actor=actor, entity=instance, changes=changes, reason=reason)


# --------------------------------------------------------------------------- verification
@dataclass(frozen=True, slots=True)
class ChainVerification:
    is_intact: bool
    checked: int
    broken_at: int | None = None
    problem: str = ""

    def __bool__(self) -> bool:
        return self.is_intact


def verify_chain(*, limit: int | None = None) -> ChainVerification:
    """Recompute the current tenant's chain and report the first break.

    Catches an altered entry, a removed entry, and an entry inserted out of order.
    """
    events = AuditEvent.objects.order_by("sequence")
    if limit is not None:
        events = events[:limit]

    expected_previous = GENESIS_HASH
    expected_sequence = 1
    checked = 0

    for event in events:
        if event.sequence != expected_sequence:
            return ChainVerification(
                is_intact=False,
                checked=checked,
                broken_at=event.sequence,
                problem=f"Expected entry #{expected_sequence}, found #{event.sequence}",
            )
        if event.previous_hash != expected_previous:
            return ChainVerification(
                is_intact=False,
                checked=checked,
                broken_at=event.sequence,
                problem="Entry does not follow the one before it",
            )
        recomputed = compute_hash(
            previous_hash=event.previous_hash,
            payload=_payload(
                sequence=event.sequence,
                action=event.action,
                actor_id=event.actor_id,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                changes=event.changes,
                reason=event.reason,
            ),
        )
        if recomputed != event.hash:
            return ChainVerification(
                is_intact=False,
                checked=checked,
                broken_at=event.sequence,
                problem="Entry contents do not match its hash",
            )
        expected_previous = event.hash
        expected_sequence += 1
        checked += 1

    return ChainVerification(is_intact=True, checked=checked)


def history_for(instance: models.Model) -> models.QuerySet[AuditEvent]:
    """Everything recorded about one record, newest first."""
    return AuditEvent.objects.filter(
        entity_type=instance._meta.label, entity_id=str(instance.pk)
    ).order_by("-sequence")
