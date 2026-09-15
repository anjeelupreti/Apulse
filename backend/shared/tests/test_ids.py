from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest

from shared import ids
from shared.ids import uuid7, uuid7_datetime


def test_uuid7_has_version_7_and_rfc_variant():
    value = uuid7()
    assert value.version == 7
    assert value.variant == "specified in RFC 4122"


def test_uuid7_is_strictly_increasing_within_a_millisecond_burst():
    values = [uuid7() for _ in range(10_000)]
    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_uuid7_stays_monotonic_when_clock_moves_backwards():
    first = uuid7()
    earlier_ns = (first.int >> 80) * 1_000_000 - 5_000_000_000
    with mock.patch.object(ids.time, "time_ns", return_value=earlier_ns):
        second = uuid7()
    assert second > first


def test_uuid7_datetime_is_close_to_now():
    created = uuid7_datetime(uuid7())
    assert abs(datetime.now(tz=UTC) - created) < timedelta(seconds=2)


def test_uuid7_datetime_rejects_other_versions():
    import uuid

    with pytest.raises(ValueError, match="Not a UUIDv7"):
        uuid7_datetime(uuid.uuid4())
