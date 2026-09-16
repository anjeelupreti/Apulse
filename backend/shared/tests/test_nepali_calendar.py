import json
from datetime import date, timedelta

import pytest

from shared.nepali_calendar import (
    BSDate,
    CalendarNotLoadedError,
    CalendarTableError,
    DateOutOfRangeError,
    ad_to_bs,
    bs_to_ad,
    is_loaded,
    load_table_from_json,
    loaded_range,
    month_name,
)
from shared.nepali_calendar.table import build_table

from .conftest import SYNTHETIC_EPOCH_DATE, SYNTHETIC_EPOCH_YEAR, SYNTHETIC_MONTHS


# --------------------------------------------------------------------------- conversion
def test_the_epoch_converts_to_its_anchor_date(calendar):
    assert bs_to_ad(BSDate(SYNTHETIC_EPOCH_YEAR, 1, 1)) == SYNTHETIC_EPOCH_DATE
    assert ad_to_bs(SYNTHETIC_EPOCH_DATE) == BSDate(SYNTHETIC_EPOCH_YEAR, 1, 1)


def test_every_date_in_the_table_survives_a_round_trip(calendar):
    """Conversion has to be exact in both directions; an invoice date cannot drift by a day."""
    for year in sorted(calendar.month_days):
        for month in range(1, 13):
            for day in (1, 15, calendar.days_in_month(year, month)):
                bs = BSDate(year, month, day)
                assert ad_to_bs(bs_to_ad(bs)) == bs


def test_consecutive_days_stay_consecutive(calendar):
    """Walk a whole year one day at a time and check nothing is skipped or repeated."""
    start = bs_to_ad(BSDate(SYNTHETIC_EPOCH_YEAR, 1, 1))
    seen = []
    for offset in range(sum(SYNTHETIC_MONTHS)):
        seen.append(ad_to_bs(start + timedelta(days=offset)))
    assert len(set(seen)) == len(seen)
    assert seen[0] == BSDate(SYNTHETIC_EPOCH_YEAR, 1, 1)
    assert seen[-1] == BSDate(SYNTHETIC_EPOCH_YEAR, 12, SYNTHETIC_MONTHS[11])


def test_month_ends_roll_over_correctly(calendar):
    last_of_baisakh = BSDate(SYNTHETIC_EPOCH_YEAR, 1, SYNTHETIC_MONTHS[0])
    assert ad_to_bs(bs_to_ad(last_of_baisakh) + timedelta(days=1)) == BSDate(
        SYNTHETIC_EPOCH_YEAR, 2, 1
    )


def test_a_day_that_does_not_exist_is_refused(calendar):
    """Baisakh has 31 days in this table, so the 32nd is not a date."""
    with pytest.raises(ValueError, match="not a real date"):
        bs_to_ad(BSDate(SYNTHETIC_EPOCH_YEAR, 1, 32))


def test_years_outside_the_table_are_refused_rather_than_guessed(calendar):
    with pytest.raises(DateOutOfRangeError, match="outside the loaded table"):
        bs_to_ad(BSDate(calendar.max_year + 1, 1, 1))
    with pytest.raises(DateOutOfRangeError, match="before the loaded table"):
        ad_to_bs(SYNTHETIC_EPOCH_DATE - timedelta(days=1))
    with pytest.raises(DateOutOfRangeError, match="after the loaded table"):
        ad_to_bs(date(2100, 1, 1))


def test_without_a_table_conversion_fails_loudly(no_calendar):
    """Silence here would mean a missing or wrong date on a document."""
    assert not is_loaded()
    assert loaded_range() is None
    with pytest.raises(CalendarNotLoadedError, match="CR-CAL-01"):
        ad_to_bs(date(2026, 9, 16))


def test_loaded_range_is_reported(calendar):
    assert loaded_range() == (calendar.min_year, calendar.max_year)


# --------------------------------------------------------------------------- BSDate
def test_bs_dates_parse_and_print():
    assert str(BSDate.parse("2082-03-15")) == "2082-03-15"


@pytest.mark.parametrize("bad", ["2082-13-01", "2082-00-01", "2082-01-33"])
def test_impossible_bs_dates_are_refused(bad):
    with pytest.raises(ValueError, match="must be"):
        BSDate.parse(bad)


def test_bs_dates_sort_chronologically():
    assert BSDate(2082, 1, 1) < BSDate(2082, 1, 2) < BSDate(2082, 2, 1) < BSDate(2083, 1, 1)


# --------------------------------------------------------------------------- table validation
def valid_months() -> list[int]:
    return list(SYNTHETIC_MONTHS)


def test_a_year_with_the_wrong_number_of_months_is_rejected():
    with pytest.raises(CalendarTableError, match="every year must have 12"):
        build_table(
            epoch_bs_year=2070,
            epoch_ad_date=SYNTHETIC_EPOCH_DATE,
            month_days={2070: [31] * 11},
        )


@pytest.mark.parametrize("bad_length", [28, 33])
def test_an_impossible_month_length_is_rejected(bad_length):
    months = valid_months()
    months[0] = bad_length
    with pytest.raises(CalendarTableError, match="expected 29-32"):
        build_table(
            epoch_bs_year=2070, epoch_ad_date=SYNTHETIC_EPOCH_DATE, month_days={2070: months}
        )


def test_a_year_that_is_not_a_solar_year_is_rejected():
    months = valid_months()
    months[0] = 29  # two days short of a year
    months[1] = 29
    with pytest.raises(CalendarTableError, match="must be 365-366"):
        build_table(
            epoch_bs_year=2070, epoch_ad_date=SYNTHETIC_EPOCH_DATE, month_days={2070: months}
        )


def test_a_gap_in_the_years_is_rejected():
    with pytest.raises(CalendarTableError, match="gap"):
        build_table(
            epoch_bs_year=2070,
            epoch_ad_date=SYNTHETIC_EPOCH_DATE,
            month_days={2070: valid_months(), 2072: valid_months()},
        )


def test_accumulated_errors_show_up_as_new_year_drift():
    """The strongest automatic check: Baisakh 1 must stay in mid-April.

    A year that is short by a day shifts every later year, and within a few years the new year
    walks out of April. This is what caught a mistake while this package was being written.
    """
    # Every year here is a legal length (366), so the per-year checks pass. What gives it away is
    # that 366 every year runs ahead of the Gregorian calendar, and within about seven years
    # Baisakh 1 has walked past mid-April.
    stretched = valid_months()
    stretched[0] = 32  # 365 + 1
    years = {2070 + offset: list(stretched) for offset in range(12)}

    with pytest.raises(CalendarTableError, match="outside mid-April"):
        build_table(epoch_bs_year=2070, epoch_ad_date=SYNTHETIC_EPOCH_DATE, month_days=years)


def test_the_epoch_must_be_the_first_year_in_the_table():
    with pytest.raises(CalendarTableError, match="must be the first year"):
        build_table(
            epoch_bs_year=2071,
            epoch_ad_date=SYNTHETIC_EPOCH_DATE,
            month_days={2070: valid_months(), 2071: valid_months()},
        )


def test_an_empty_table_is_rejected():
    with pytest.raises(CalendarTableError, match="empty"):
        build_table(epoch_bs_year=2070, epoch_ad_date=SYNTHETIC_EPOCH_DATE, month_days={})


# --------------------------------------------------------------------------- loading
def test_a_table_loads_from_json(tmp_path):
    path = tmp_path / "bs.json"
    path.write_text(
        json.dumps(
            {
                "source": "test fixture",
                "epoch_bs_year": 2070,
                "epoch_ad_date": "2013-04-14",
                "month_days": {"2070": valid_months(), "2071": valid_months()},
            }
        ),
        encoding="utf-8",
    )
    table = load_table_from_json(path)
    assert table.min_year == 2070
    assert table.max_year == 2071
    assert table.source == "test fixture"


def test_a_missing_file_is_reported_clearly(tmp_path):
    with pytest.raises(CalendarTableError, match="not found"):
        load_table_from_json(tmp_path / "nope.json")


def test_a_file_missing_a_key_is_reported_clearly(tmp_path):
    path = tmp_path / "bs.json"
    path.write_text(json.dumps({"epoch_bs_year": 2070}), encoding="utf-8")
    with pytest.raises(CalendarTableError, match="missing"):
        load_table_from_json(path)


# --------------------------------------------------------------------------- names
def test_month_names_in_both_languages():
    assert month_name(1) == "Baisakh"
    assert month_name(4, "ne") == "साउन"
    assert month_name(12, "en") == "Chaitra"


def test_an_impossible_month_number_is_refused():
    with pytest.raises(ValueError, match="1-12"):
        month_name(13)
