"""Test fixtures shared by the whole backend suite."""

from collections.abc import Iterator

import pytest
from django.core.cache import cache

from shared.nepali_calendar.table import CalendarTable, current_table, load_table
from shared.nepali_calendar.testing import synthetic_table


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Sign-in lockout, API throttling and entitlements are cache-backed.

    Without this, counters accumulated by one test would lock out or throttle the next one, and
    test order would decide whether the suite passed.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def calendar() -> Iterator[CalendarTable]:
    """Load a synthetic Bikram Sambat table for one test.

    No real table ships with the code (CR-CAL-01), so anything that needs BS dates or fiscal
    years asks for this fixture.
    """
    previous = current_table()
    table = synthetic_table()
    load_table(table)
    try:
        yield table
    finally:
        load_table(previous)


@pytest.fixture
def no_calendar() -> Iterator[None]:
    previous = current_table()
    load_table(None)
    try:
        yield
    finally:
        load_table(previous)
