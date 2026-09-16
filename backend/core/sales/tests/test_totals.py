"""Invoice arithmetic on its own."""

from decimal import Decimal

import pytest

from core.sales.totals import NO_ROUNDING, compute_line, compute_totals


def line(**overrides):
    defaults = {
        "quantity": Decimal("10"),
        "rate": Decimal("100"),
        "tax_percentage": Decimal("13"),
        "price_includes_tax": True,
    }
    return compute_line(**{**defaults, **overrides})


def test_a_shelf_price_already_contains_its_tax():
    """A pharmacy prices at MRP, so the tax comes out of the price rather than being added."""
    amounts = line()
    assert amounts.net == Decimal("1000.00")
    assert amounts.taxable == Decimal("884.96")
    assert amounts.tax == Decimal("115.04")
    assert amounts.total == Decimal("1000.00")


def test_tax_can_be_added_on_top_instead():
    """A wholesale invoice to another business usually quotes prices before tax."""
    amounts = line(price_includes_tax=False)
    assert amounts.taxable == Decimal("1000.00")
    assert amounts.tax == Decimal("130.00")
    assert amounts.total == Decimal("1130.00")


def test_an_exempt_item_is_not_taxed():
    amounts = line(tax_percentage=Decimal("0"))
    assert amounts.tax == Decimal("0.00")
    assert amounts.taxable == Decimal("1000.00")


def test_a_discount_comes_off_before_tax_is_worked_out():
    amounts = line(discount_percent=Decimal("10"))
    assert amounts.discount == Decimal("100.00")
    assert amounts.net == Decimal("900.00")
    assert amounts.total == Decimal("900.00")


def test_the_parts_of_a_line_always_add_up():
    for quantity in ("1", "3", "7.5", "99"):
        for rate in ("0.50", "13.33", "999.99"):
            amounts = line(quantity=Decimal(quantity), rate=Decimal(rate))
            assert amounts.taxable + amounts.tax == amounts.net


# --------------------------------------------------------------------------- totals
def test_totals_add_the_lines_up():
    totals = compute_totals([line(), line()], rounding_step=NO_ROUNDING)
    assert totals.taxable == Decimal("1769.92")
    assert totals.tax == Decimal("230.08")
    assert totals.subtotal == Decimal("2000.00")
    assert totals.payable == Decimal("2000.00")


def test_the_total_rounds_to_the_nearest_rupee():
    """Counters deal in whole rupees; the difference is shown, not hidden."""
    totals = compute_totals(
        [line(quantity=Decimal("1"), rate=Decimal("99.60"))], rounding_step=Decimal("1")
    )
    assert totals.subtotal == Decimal("99.60")
    assert totals.payable == Decimal("100.00")
    assert totals.rounding == Decimal("0.40")


def test_rounding_can_go_down_as_well():
    totals = compute_totals(
        [line(quantity=Decimal("1"), rate=Decimal("99.20"))], rounding_step=Decimal("1")
    )
    assert totals.payable == Decimal("99.00")
    assert totals.rounding == Decimal("-0.20")


def test_rounding_is_applied_once_to_the_total_not_to_each_line():
    """Rounding each line would make the invoice's own arithmetic fail to add up."""
    lines = [line(quantity=Decimal("1"), rate=Decimal("0.40")) for _ in range(5)]
    totals = compute_totals(lines, rounding_step=Decimal("1"))
    assert totals.subtotal == Decimal("2.00")
    assert totals.payable == Decimal("2.00")


def test_the_subtotal_always_equals_its_parts():
    totals = compute_totals([line(), line(rate=Decimal("33.33"))], rounding_step=NO_ROUNDING)
    assert totals.taxable + totals.tax == totals.subtotal


def test_payable_always_equals_subtotal_plus_rounding():
    for rate in ("99.60", "0.10", "1234.56"):
        totals = compute_totals(
            [line(quantity=Decimal("1"), rate=Decimal(rate))], rounding_step=Decimal("1")
        )
        assert totals.subtotal + totals.rounding == totals.payable


@pytest.mark.parametrize("step", ["1", "0.01", "0.05"])
def test_any_rounding_step_still_balances(step):
    totals = compute_totals([line(rate=Decimal("77.77"))], rounding_step=Decimal(step))
    assert totals.subtotal + totals.rounding == totals.payable


def test_an_empty_bill_comes_to_nothing():
    totals = compute_totals([], rounding_step=Decimal("1"))
    assert totals.payable == Decimal("0.00")
