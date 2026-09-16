"""Nepal's fiscal year: Shrawan 1 to the last day of Ashadh.

Invoice numbering resets here, VAT returns are filed against it, and every report a pharmacy owes
IRD is bounded by it — so it is worth being exact about, rather than approximating with a
Gregorian year.
"""

from dataclasses import dataclass
from datetime import date

from .convert import ad_to_bs, bs_to_ad
from .names import FISCAL_YEAR_START_MONTH
from .table import BSDate, current_table


@dataclass(frozen=True, slots=True)
class FiscalYear:
    #: The BS year the fiscal year starts in; 2082 for 2082/83.
    start_year: int
    start_bs: BSDate
    end_bs: BSDate
    start_ad: date
    end_ad: date

    @property
    def label(self) -> str:
        """`2082/83`, the form used on invoices and IRD filings."""
        return f"{self.start_year}/{(self.start_year + 1) % 100:02d}"

    @property
    def short_label(self) -> str:
        """`8283`, for document numbers where a slash is awkward."""
        return f"{self.start_year % 100:02d}{(self.start_year + 1) % 100:02d}"

    def contains_ad(self, value: date) -> bool:
        return self.start_ad <= value <= self.end_ad

    def __str__(self) -> str:
        return self.label


def fiscal_year_for_bs(bs: BSDate) -> FiscalYear:
    """The fiscal year a BS date falls in.

    Baisakh, Jestha and Ashadh belong to the fiscal year that began the previous Shrawan.
    """
    start_year = bs.year if bs.month >= FISCAL_YEAR_START_MONTH else bs.year - 1
    return _build(start_year)


def fiscal_year_for_ad(value: date) -> FiscalYear:
    return fiscal_year_for_bs(ad_to_bs(value))


def fiscal_year_from_label(label: str) -> FiscalYear:
    """Read `2082/83` or `2082/2083` or `2082`."""
    start = label.strip().split("/")[0]
    if not start.isdigit():
        raise ValueError(f"Expected a fiscal year such as 2082/83, got {label!r}")
    return _build(int(start))


def _build(start_year: int) -> FiscalYear:
    table = current_table()
    if table is None:
        from .convert import CalendarNotLoadedError

        raise CalendarNotLoadedError

    end_year = start_year + 1
    last_month_of_fiscal_year = FISCAL_YEAR_START_MONTH - 1  # Ashadh
    last_day = table.days_in_month(end_year, last_month_of_fiscal_year)

    start_bs = BSDate(start_year, FISCAL_YEAR_START_MONTH, 1)
    end_bs = BSDate(end_year, last_month_of_fiscal_year, last_day)
    return FiscalYear(
        start_year=start_year,
        start_bs=start_bs,
        end_bs=end_bs,
        start_ad=bs_to_ad(start_bs),
        end_ad=bs_to_ad(end_bs),
    )
