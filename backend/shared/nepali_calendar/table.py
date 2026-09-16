"""The calendar table, and the checks a table must pass before it is trusted."""

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

MONTHS_IN_YEAR = 12
#: Month lengths in BS run from 29 to 32 days. Anything outside this is a transcription error.
MIN_MONTH_DAYS = 29
MAX_MONTH_DAYS = 32
#: A BS year is one solar year, so it must be 365 or 366 days.
MIN_YEAR_DAYS = 365
MAX_YEAR_DAYS = 366
#: Baisakh 1 always lands in mid-April. Accumulated month-length errors show up as drift out of
#: this window, which is the strongest automatic check available without a second source.
NEW_YEAR_EARLIEST = (4, 10)
NEW_YEAR_LATEST = (4, 18)


class CalendarTableError(ValueError):
    """The calendar table is malformed or internally inconsistent."""


@dataclass(frozen=True, slots=True, order=True)
class BSDate:
    year: int
    month: int
    day: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= MONTHS_IN_YEAR:
            raise ValueError(f"Month must be 1-12, got {self.month}")
        if not 1 <= self.day <= MAX_MONTH_DAYS:
            raise ValueError(f"Day must be 1-32, got {self.day}")

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"

    @classmethod
    def parse(cls, value: str) -> "BSDate":
        """Read `2082-03-15`."""
        parts = value.strip().split("-")
        if len(parts) != 3:
            raise ValueError(f"Expected a BS date as YYYY-MM-DD, got {value!r}")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))


@dataclass(frozen=True, slots=True)
class CalendarTable:
    """Month lengths per BS year, anchored to one known Gregorian date."""

    #: Baisakh 1 of `epoch_bs_year` fell on this Gregorian date.
    epoch_bs_year: int
    epoch_ad_date: date
    month_days: dict[int, tuple[int, ...]]
    source: str = ""
    #: Gregorian date of Baisakh 1 for each year, computed once when the table is loaded.
    year_starts: dict[int, date] = field(default_factory=dict, compare=False)

    @property
    def min_year(self) -> int:
        return min(self.month_days)

    @property
    def max_year(self) -> int:
        return max(self.month_days)

    def days_in_month(self, year: int, month: int) -> int:
        try:
            return self.month_days[year][month - 1]
        except KeyError:
            raise CalendarTableError(f"BS year {year} is not in the loaded table") from None

    def days_in_year(self, year: int) -> int:
        return sum(self.month_days[year])


def build_table(
    *,
    epoch_bs_year: int,
    epoch_ad_date: date,
    month_days: dict[int, list[int] | tuple[int, ...]],
    source: str = "",
) -> CalendarTable:
    """Validate a table and precompute the Gregorian start of every year."""
    normalised = {
        int(year): tuple(int(days) for days in months) for year, months in month_days.items()
    }
    _check_shape(normalised)

    years = sorted(normalised)
    if epoch_bs_year != years[0]:
        raise CalendarTableError(
            f"The epoch year {epoch_bs_year} must be the first year in the table ({years[0]})"
        )
    if any(second - first != 1 for first, second in pairwise(years)):
        raise CalendarTableError("The table has a gap: BS years must be consecutive")

    year_starts: dict[int, date] = {}
    cursor = epoch_ad_date
    for year in years:
        year_starts[year] = cursor
        cursor += timedelta(days=sum(normalised[year]))

    _check_new_year_drift(year_starts)

    return CalendarTable(
        epoch_bs_year=epoch_bs_year,
        epoch_ad_date=epoch_ad_date,
        month_days=normalised,
        source=source,
        year_starts=year_starts,
    )


def _check_shape(month_days: dict[int, tuple[int, ...]]) -> None:
    if not month_days:
        raise CalendarTableError("The calendar table is empty")
    for year, months in sorted(month_days.items()):
        if len(months) != MONTHS_IN_YEAR:
            raise CalendarTableError(
                f"BS {year} has {len(months)} months; every year must have {MONTHS_IN_YEAR}"
            )
        for index, days in enumerate(months, start=1):
            if not MIN_MONTH_DAYS <= days <= MAX_MONTH_DAYS:
                raise CalendarTableError(
                    f"BS {year} month {index} is {days} days; expected "
                    f"{MIN_MONTH_DAYS}-{MAX_MONTH_DAYS}"
                )
        total = sum(months)
        if not MIN_YEAR_DAYS <= total <= MAX_YEAR_DAYS:
            raise CalendarTableError(
                f"BS {year} totals {total} days; a solar year must be "
                f"{MIN_YEAR_DAYS}-{MAX_YEAR_DAYS}"
            )


def _check_new_year_drift(year_starts: dict[int, date]) -> None:
    """Every Baisakh 1 must land in mid-April.

    This catches accumulated month-length errors: one wrong month shifts every later year, and the
    new year walks out of April within a few years. It cannot catch a single year that is one day
    out and corrected the next, which is why a second source is still required (CR-CAL-01).
    """
    for year, start in sorted(year_starts.items()):
        if not (NEW_YEAR_EARLIEST <= (start.month, start.day) <= NEW_YEAR_LATEST):
            raise CalendarTableError(
                f"Baisakh 1 of BS {year} works out as {start.isoformat()}, which is outside "
                f"mid-April. The month lengths before BS {year} do not add up."
            )


def load_table_from_json(path: Path | str) -> CalendarTable:
    """Read a table file.

    Expected shape::

        {
          "source": "Nepali Patro / Department of Survey, checked 2026-09-16",
          "epoch_bs_year": 2070,
          "epoch_ad_date": "2013-04-14",
          "month_days": {"2070": [31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30], ...}
        }
    """
    path = Path(path)
    if not path.is_file():
        raise CalendarTableError(f"Calendar table file not found: {path}")
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    try:
        return build_table(
            epoch_bs_year=int(raw["epoch_bs_year"]),
            epoch_ad_date=date.fromisoformat(raw["epoch_ad_date"]),
            month_days=raw["month_days"],
            source=raw.get("source", str(path)),
        )
    except KeyError as missing:
        raise CalendarTableError(f"Calendar table is missing {missing}") from None


_table: CalendarTable | None = None


def load_table(table: CalendarTable | None) -> None:
    """Install the table the process will use. Passing None unloads it."""
    global _table
    _table = table


def current_table() -> CalendarTable | None:
    return _table
