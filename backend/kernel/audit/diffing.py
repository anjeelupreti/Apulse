"""Turning model changes into something readable years later."""

import hashlib
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import models

from shared.redaction import MASK, is_sensitive


def jsonable(value: Any) -> Any:
    """A JSON-safe representation that a person can still read."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, models.Model):
        return str(value.pk)
    if isinstance(value, list | tuple | set):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    return str(value)


def _field_value(instance: models.Model, field: models.Field[Any, Any]) -> Any:
    """One field, shaped the way the database holds it.

    A decimal is quantized to the column's scale. Without that, an amount set in memory as
    `Decimal("50000")` and the same amount read back as `Decimal("50000.0000")` look like
    different values, and every subsequent save of an untouched row would be recorded as a change.
    """
    raw = getattr(instance, field.attname, None)
    if isinstance(raw, Decimal) and isinstance(field, models.DecimalField):
        places = field.decimal_places or 0
        return raw.quantize(Decimal(1).scaleb(-places))
    return raw


def snapshot(instance: models.Model) -> dict[str, Any]:
    """Field values of an instance, with secrets masked. This is the form that gets stored.

    Uses `attname`, so a foreign key is recorded as the id it points at rather than triggering a
    query for the related object.
    """
    return {
        field.name: MASK if is_sensitive(field.name) else jsonable(_field_value(instance, field))
        for field in instance._meta.concrete_fields
    }


def fingerprint(value: Any) -> str:
    """A short digest, so a secret can be compared without being stored.

    Not reversible and not a password hash — it exists only so that "this changed" is answerable
    for a field whose value must never be written into the trail.
    """
    return hashlib.sha256(repr(value).encode()).hexdigest()[:16]


def comparable(instance: models.Model) -> dict[str, Any]:
    """The form to compare two versions of a row with.

    Identical to `snapshot` except that a masked field carries a digest of its value. Without it
    both sides of a password change read `***`, they compare equal, and the one fact the trail is
    supposed to keep — that it changed, and when — is lost.
    """
    values: dict[str, Any] = {}
    for field in instance._meta.concrete_fields:
        raw = _field_value(instance, field)
        if is_sensitive(field.name):
            values[field.name] = f"{MASK}{fingerprint(raw)}"
        else:
            values[field.name] = jsonable(raw)
    return values


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Only what actually changed, as `{field: {"from": ..., "to": ...}}`.

    Masked fields are reported as changed without revealing either value, because "the password
    was changed at 14:02" is the useful fact and the value never is.
    """
    changes: dict[str, dict[str, Any]] = {}
    for name in sorted(set(before) | set(after)):
        old = before.get(name)
        new = after.get(name)
        if old == new:
            continue
        if is_sensitive(name):
            changes[name] = {"from": MASK, "to": MASK}
        else:
            changes[name] = {"from": old, "to": new}
    return changes
