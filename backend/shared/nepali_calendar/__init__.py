"""Bikram Sambat: the calendar Nepal actually runs on.

Invoice dates, fiscal years, licence expiries and register entries are all BS. There is no formula
for it — the length of each month varies year to year and is published, not computed — so this
package is a conversion engine plus a table that must be loaded from an authoritative source.

Nothing is bundled on purpose. A month length that is one day out silently shifts the date printed
on a tax invoice and can move a transaction into the wrong fiscal year. See COMPLIANCE_REGISTER
CR-CAL-01.
"""

from .convert import (
    CalendarNotLoadedError,
    DateOutOfRangeError,
    ad_to_bs,
    bs_to_ad,
    is_loaded,
    loaded_range,
)
from .fiscal import FiscalYear, fiscal_year_for_ad, fiscal_year_for_bs, fiscal_year_from_label
from .names import MONTH_NAMES_EN, MONTH_NAMES_NE, month_name
from .table import BSDate, CalendarTable, CalendarTableError, load_table, load_table_from_json

__all__ = (
    "MONTH_NAMES_EN",
    "MONTH_NAMES_NE",
    "BSDate",
    "CalendarNotLoadedError",
    "CalendarTable",
    "CalendarTableError",
    "DateOutOfRangeError",
    "FiscalYear",
    "ad_to_bs",
    "bs_to_ad",
    "fiscal_year_for_ad",
    "fiscal_year_for_bs",
    "fiscal_year_from_label",
    "is_loaded",
    "load_table",
    "load_table_from_json",
    "loaded_range",
    "month_name",
)
