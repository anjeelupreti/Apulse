from collections.abc import Iterator
from datetime import date

import pytest

from shared.nepali_calendar.table import CalendarTable, build_table, current_table, load_table

#: Sums to 365. Enough to exercise the engine without pretending to be the real calendar.
SYNTHETIC_MONTHS = (31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30)
SYNTHETIC_EPOCH_YEAR = 2070
SYNTHETIC_EPOCH_DATE = date(2013, 4, 14)


def make_table(years: int = 8) -> CalendarTable:
    return build_table(
        epoch_bs_year=SYNTHETIC_EPOCH_YEAR,
        epoch_ad_date=SYNTHETIC_EPOCH_DATE,
        month_days={
            SYNTHETIC_EPOCH_YEAR + offset: list(SYNTHETIC_MONTHS) for offset in range(years)
        },
        source="synthetic table for tests",
    )


@pytest.fixture
def calendar() -> Iterator[CalendarTable]:
    """Load a synthetic table for the duration of one test.

    The engine is what these tests check. The real table is supplied per deployment and verified
    separately (CR-CAL-01), so tests must not depend on its contents.
    """
    previous = current_table()
    table = make_table()
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
