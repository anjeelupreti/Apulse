"""Turning model changes into something readable years later."""

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


def snapshot(instance: models.Model) -> dict[str, Any]:
    """Field values of an instance, with secrets masked.

    Uses `attname`, so a foreign key is recorded as the id it points at rather than triggering a
    query for the related object.
    """
    values: dict[str, Any] = {}
    for field in instance._meta.concrete_fields:
        name = field.name
        raw = getattr(instance, field.attname, None)
        values[name] = MASK if is_sensitive(name) else jsonable(raw)
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
