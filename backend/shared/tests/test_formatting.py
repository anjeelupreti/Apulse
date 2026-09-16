from decimal import Decimal

import pytest

from shared.formatting import (
    amount_in_words_en,
    format_npr,
    group_digits,
    number_in_words_en,
    quantize_money,
    to_ascii_digits,
    to_devanagari_digits,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (999, "999"),
        (1000, "1,000"),
        (99999, "99,999"),
        (100000, "1,00,000"),  # one lakh, not 100,000
        (1234567, "12,34,567"),
        (12345678, "1,23,45,678"),  # one crore
        (1234567890, "1,23,45,67,890"),
        (-100000, "-1,00,000"),
    ],
)
def test_digits_group_the_south_asian_way(value, expected):
    assert group_digits(value) == expected


def test_grouping_keeps_the_decimal_part_intact():
    assert group_digits(Decimal("123456.75")) == "1,23,456.75"


def test_devanagari_digits_round_trip():
    assert to_devanagari_digits("2082-03-15") == "२०८२-०३-१५"
    assert to_ascii_digits("२०८२-०३-१५") == "2082-03-15"


def test_only_digits_change_in_devanagari():
    assert to_devanagari_digits("INV-KTM01-2082/83-000123").startswith("INV-KTM")


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("1234.5"), "रू 1,234.50"),
        (Decimal("100000"), "रू 1,00,000.00"),
        (Decimal("-250.255"), "-रू 250.26"),  # rounds half up
    ],
)
def test_money_is_formatted_for_nepal(amount, expected):
    assert format_npr(amount) == expected


def test_money_can_be_shown_without_a_symbol_or_in_devanagari():
    assert format_npr(Decimal("1500"), symbol=False) == "1,500.00"
    assert format_npr(Decimal("1500"), devanagari=True) == to_devanagari_digits("रू 1,500.00")


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("0.005", Decimal("0.01")),  # half up, the way a cashier expects
        ("2.344", Decimal("2.34")),
        ("2.345", Decimal("2.35")),
    ],
)
def test_money_rounds_half_up(amount, expected):
    assert quantize_money(amount) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (0, "zero"),
        (7, "seven"),
        (15, "fifteen"),
        (21, "twenty-one"),
        (100, "one hundred"),
        (101, "one hundred one"),
        (999, "nine hundred ninety-nine"),
        (1000, "one thousand"),
        (25000, "twenty-five thousand"),
        (100000, "one lakh"),
        (150000, "one lakh fifty thousand"),
        (1234567, "twelve lakh thirty-four thousand five hundred sixty-seven"),
        (10000000, "one crore"),
        (1000000000, "one hundred crore"),
    ],
)
def test_numbers_in_words_use_lakh_and_crore(number, expected):
    """Never "million": a Nepali invoice reads in lakh and crore."""
    assert number_in_words_en(number) == expected


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("0", "Zero rupees only"),
        ("1", "One rupees only"),
        ("100", "One hundred rupees only"),
        ("1234.50", "One thousand two hundred thirty-four rupees and fifty paisa only"),
        (
            "123456.50",
            "One lakh twenty-three thousand four hundred fifty-six rupees and fifty paisa only",
        ),
        ("0.05", "Zero rupees and five paisa only"),
    ],
)
def test_totals_in_words_for_a_tax_invoice(amount, expected):
    """IRD requires the total in words on a tax invoice."""
    assert amount_in_words_en(Decimal(amount)) == expected


def test_words_start_with_a_capital():
    assert amount_in_words_en(Decimal("5")).startswith("Five")


def test_a_negative_total_reads_as_negative():
    assert amount_in_words_en(Decimal("-5")) == "Minus five rupees only"


def test_paisa_are_rounded_before_being_spelled():
    assert amount_in_words_en(Decimal("10.567")) == "Ten rupees and fifty-seven paisa only"
