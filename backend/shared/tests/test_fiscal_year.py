"""Nepal's fiscal year runs Shrawan to Ashadh, not January to December."""

from datetime import date, timedelta

import pytest

from shared.nepali_calendar import (
    BSDate,
    bs_to_ad,
    fiscal_year_for_ad,
    fiscal_year_for_bs,
    fiscal_year_from_label,
)


def test_the_year_starts_on_the_first_of_shrawan(calendar):
    year = fiscal_year_from_label("2071/72")
    assert year.start_bs == BSDate(2071, 4, 1)
    assert year.start_ad == bs_to_ad(BSDate(2071, 4, 1))


def test_the_year_ends_on_the_last_day_of_ashadh(calendar):
    year = fiscal_year_from_label("2071/72")
    last_of_ashadh = calendar.days_in_month(2072, 3)
    assert year.end_bs == BSDate(2072, 3, last_of_ashadh)
    # And the next fiscal year begins the very next day.
    assert fiscal_year_from_label("2072/73").start_ad == year.end_ad + timedelta(days=1)


@pytest.mark.parametrize(
    ("month", "expected_start_year"),
    [
        (1, 2070),  # Baisakh belongs to the fiscal year that began last Shrawan
        (2, 2070),  # Jestha
        (3, 2070),  # Ashadh, the final month
        (4, 2071),  # Shrawan starts the new one
        (12, 2071),  # Chaitra
    ],
)
def test_which_fiscal_year_a_month_belongs_to(calendar, month, expected_start_year):
    assert fiscal_year_for_bs(BSDate(2071, month, 15)).start_year == expected_start_year


def test_labels_are_written_the_way_invoices_write_them(calendar):
    year = fiscal_year_from_label("2071/72")
    assert year.label == "2071/72"
    assert year.short_label == "7172"
    assert str(year) == "2071/72"


def test_a_century_boundary_still_reads_correctly():
    """2099/00, not 2099/100."""
    from shared.nepali_calendar.table import build_table, current_table, load_table

    from .conftest import SYNTHETIC_MONTHS

    previous = current_table()
    load_table(
        build_table(
            epoch_bs_year=2099,
            epoch_ad_date=date(2042, 4, 14),
            month_days={2099: list(SYNTHETIC_MONTHS), 2100: list(SYNTHETIC_MONTHS)},
        )
    )
    try:
        assert fiscal_year_from_label("2099").label == "2099/00"
    finally:
        load_table(previous)


@pytest.mark.parametrize("written", ["2071/72", "2071/2072", "2071", " 2071/72 "])
def test_labels_are_read_in_the_forms_people_write_them(calendar, written):
    assert fiscal_year_from_label(written).start_year == 2071


def test_nonsense_labels_are_refused(calendar):
    with pytest.raises(ValueError, match="Expected a fiscal year"):
        fiscal_year_from_label("last year")


def test_a_gregorian_date_finds_its_fiscal_year(calendar):
    start = bs_to_ad(BSDate(2071, 4, 1))
    year = fiscal_year_for_ad(start)
    assert year.start_year == 2071
    assert year.contains_ad(start)
    assert not year.contains_ad(start - timedelta(days=1))


def test_the_day_before_shrawan_belongs_to_the_previous_year(calendar):
    start = bs_to_ad(BSDate(2071, 4, 1))
    assert fiscal_year_for_ad(start - timedelta(days=1)).start_year == 2070


def test_every_day_of_a_fiscal_year_maps_back_to_it(calendar):
    year = fiscal_year_from_label("2071/72")
    day = year.start_ad
    while day <= year.end_ad:
        assert fiscal_year_for_ad(day).start_year == 2071
        day += timedelta(days=1)
