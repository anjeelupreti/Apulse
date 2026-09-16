"""Converting between Bikram Sambat and Gregorian dates."""

from bisect import bisect_right
from datetime import date, timedelta

from .table import BSDate, CalendarTable, current_table


class CalendarNotLoadedError(RuntimeError):
    """No calendar table has been loaded, so BS dates cannot be produced."""

    def __init__(self) -> None:
        super().__init__(
            "No Bikram Sambat table is loaded. Set BACKEND_BS_CALENDAR_FILE to a verified "
            "table (see COMPLIANCE_REGISTER CR-CAL-01)."
        )


class DateOutOfRangeError(ValueError):
    """The date falls outside the years the loaded table covers."""


def _require_table() -> CalendarTable:
    table = current_table()
    if table is None:
        raise CalendarNotLoadedError
    return table


def is_loaded() -> bool:
    return current_table() is not None


def loaded_range() -> tuple[int, int] | None:
    """The BS years the loaded table covers, or None if nothing is loaded."""
    table = current_table()
    return None if table is None else (table.min_year, table.max_year)


def bs_to_ad(bs: BSDate) -> date:
    table = _require_table()
    if bs.year not in table.month_days:
        raise DateOutOfRangeError(
            f"BS {bs.year} is outside the loaded table ({table.min_year}-{table.max_year})"
        )

    months = table.month_days[bs.year]
    if bs.day > months[bs.month - 1]:
        raise ValueError(
            f"{bs} is not a real date: month {bs.month} of BS {bs.year} has "
            f"{months[bs.month - 1]} days"
        )

    offset = sum(months[: bs.month - 1]) + (bs.day - 1)
    return table.year_starts[bs.year] + timedelta(days=offset)


def ad_to_bs(value: date) -> BSDate:
    table = _require_table()
    years = sorted(table.year_starts)
    starts = [table.year_starts[year] for year in years]

    if value < starts[0]:
        raise DateOutOfRangeError(
            f"{value.isoformat()} is before the loaded table begins ({starts[0].isoformat()})"
        )

    index = bisect_right(starts, value) - 1
    year = years[index]
    remaining = (value - starts[index]).days

    months = table.month_days[year]
    if remaining >= sum(months):
        raise DateOutOfRangeError(
            f"{value.isoformat()} is after the loaded table ends (BS {table.max_year})"
        )

    for month_index, length in enumerate(months, start=1):
        if remaining < length:
            return BSDate(year, month_index, remaining + 1)
        remaining -= length

    # Unreachable: the bounds check above guarantees the loop returns.
    raise DateOutOfRangeError(f"{value.isoformat()} could not be placed in BS {year}")
