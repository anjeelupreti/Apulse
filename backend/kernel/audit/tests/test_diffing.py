from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from kernel.audit.diffing import diff, jsonable, snapshot
from kernel.identity.models import User
from shared.redaction import MASK


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (True, True),
        (7, 7),
        ("text", "text"),
        (Decimal("12.50"), "12.50"),  # str, never float: money must not lose precision
        (date(2026, 9, 16), "2026-09-16"),
        (UUID("00000000-0000-7000-8000-000000000000"), "00000000-0000-7000-8000-000000000000"),
        ([1, Decimal("2.5")], [1, "2.5"]),
    ],
)
def test_values_are_recorded_readably(value, expected):
    assert jsonable(value) == expected


@pytest.mark.django_db
def test_snapshot_masks_secrets():
    user = User.objects.create_user("ram@example.com", "a-real-password", full_name="Ram")
    values = snapshot(user)
    assert values["email"] == "ram@example.com"
    assert values["password"] == MASK
    assert "a-real-password" not in str(values)


def test_diff_reports_only_what_changed():
    changed = diff(
        {"name": "Alpha", "phone": "+9779812345678", "is_active": True},
        {"name": "Alpha Pharmacy", "phone": "+9779812345678", "is_active": True},
    )
    assert changed == {"name": {"from": "Alpha", "to": "Alpha Pharmacy"}}


def test_diff_records_that_a_secret_changed_without_revealing_it():
    changed = diff({"password": "old-hash"}, {"password": "new-hash"})
    assert changed == {"password": {"from": MASK, "to": MASK}}


def test_diff_handles_fields_appearing_and_disappearing():
    changed = diff({"a": 1}, {"b": 2})
    assert changed == {"a": {"from": 1, "to": None}, "b": {"from": None, "to": 2}}


def test_no_changes_is_an_empty_diff():
    assert diff({"a": 1}, {"a": 1}) == {}
