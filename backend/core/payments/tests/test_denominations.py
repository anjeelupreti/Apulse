"""Counting a drawer in Nepali notes and coins. No database needed."""

from decimal import Decimal

import pytest

from core.payments.denominations import (
    DENOMINATIONS,
    break_down,
    count_total,
    needs_explanation,
    unknown_values,
)


def test_the_notes_and_coins_are_the_ones_in_circulation():
    assert DENOMINATIONS == (1000, 500, 100, 50, 20, 10, 5, 2, 1)


def test_the_largest_comes_first_because_that_is_how_a_drawer_is_counted():
    assert list(DENOMINATIONS) == sorted(DENOMINATIONS, reverse=True)


def test_a_sheet_adds_up():
    assert count_total({1000: 12, 500: 3, 100: 7, 5: 1}) == Decimal("14205.00")


def test_an_empty_drawer_counts_as_nothing():
    assert count_total({}) == Decimal("0.00")


@pytest.mark.parametrize("value", [200, 250, 25, 0, 3])
def test_something_that_is_not_a_nepali_note_is_spotted(value):
    assert unknown_values({1000: 1, value: 1}) == (value,)


def test_a_rupee_either_way_needs_no_essay():
    """Demanding a paragraph for a one-rupee difference only teaches people to type "ok"."""
    assert not needs_explanation(Decimal("1.00"))
    assert not needs_explanation(Decimal("-1.00"))
    assert needs_explanation(Decimal("1.01"))
    assert needs_explanation(Decimal("-400.00"))


def test_change_comes_out_in_the_fewest_notes():
    assert break_down(Decimal("1687")) == {1000: 1, 500: 1, 100: 1, 50: 1, 20: 1, 10: 1, 5: 1, 2: 1}


def test_paisa_are_dropped_because_nothing_smaller_than_a_rupee_circulates():
    assert break_down(Decimal("99.75")) == {50: 1, 20: 2, 5: 1, 2: 2}


def test_nothing_owed_breaks_down_to_nothing():
    assert break_down(0) == {}
