"""A synthetic calendar table for tests.

Tests must not depend on the real table: it is supplied per deployment and verified separately
(CR-CAL-01). What tests check is the engine — conversion, fiscal years, numbering — and for that
a consistent made-up table is not only sufficient but preferable, because it cannot drift when the
real data is loaded.
"""

from datetime import date

from .table import CalendarTable, build_table

#: Sums to 365.
SYNTHETIC_MONTHS: tuple[int, ...] = (31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30)
SYNTHETIC_EPOCH_YEAR = 2070
SYNTHETIC_EPOCH_DATE = date(2013, 4, 14)


def synthetic_table(years: int = 8) -> CalendarTable:
    return build_table(
        epoch_bs_year=SYNTHETIC_EPOCH_YEAR,
        epoch_ad_date=SYNTHETIC_EPOCH_DATE,
        month_days={
            SYNTHETIC_EPOCH_YEAR + offset: list(SYNTHETIC_MONTHS) for offset in range(years)
        },
        source="synthetic table for tests",
    )
