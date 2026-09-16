"""The arithmetic of what stock cost, on its own."""

from decimal import Decimal

import pytest

from core.purchasing.costing import allocate_freight, cost_line


def costing(**overrides):
    defaults = {
        "charged_base_quantity": Decimal("100"),
        "free_base_quantity": Decimal("0"),
        "net_amount": Decimal("1000"),
        "vat_is_recoverable": True,
    }
    return cost_line(**{**defaults, **overrides})


def test_plain_cost_is_amount_over_quantity():
    assert costing().unit_cost == Decimal("10.0000")


def test_free_quantity_lowers_the_cost_of_everything():
    """'10 + 1 free' means eleven units cost what ten were charged for."""
    result = costing(charged_base_quantity=Decimal("100"), free_base_quantity=Decimal("10"))
    assert result.total_base_quantity == Decimal("110")
    assert result.unit_cost == Decimal("9.0909")
    # Ignoring the bonus would overstate cost, and understate margin on every later sale.
    assert result.unit_cost_ignoring_bonus == Decimal("10.0000")


def test_the_value_of_a_bonus_deal_can_be_shown():
    result = costing(charged_base_quantity=Decimal("100"), free_base_quantity=Decimal("10"))
    assert result.bonus_saving_percent == Decimal("9.0910")


def test_freight_is_part_of_what_stock_cost():
    result = costing(freight_share=Decimal("200"))
    assert result.total_cost == Decimal("1200")
    assert result.unit_cost == Decimal("12.0000")


def test_recoverable_vat_is_not_part_of_cost():
    """A VAT-registered pharmacy reclaims input VAT, so it never formed part of the cost."""
    result = costing(tax_amount=Decimal("130"), vat_is_recoverable=True)
    assert result.non_recoverable_tax == Decimal("0")
    assert result.unit_cost == Decimal("10.0000")


def test_vat_a_pharmacy_cannot_reclaim_is_part_of_cost():
    """One below the VAT threshold pays it and never gets it back."""
    result = costing(tax_amount=Decimal("130"), vat_is_recoverable=False)
    assert result.non_recoverable_tax == Decimal("130")
    assert result.unit_cost == Decimal("11.3000")


def test_everything_together():
    result = costing(
        charged_base_quantity=Decimal("100"),
        free_base_quantity=Decimal("20"),
        net_amount=Decimal("1000"),
        freight_share=Decimal("50"),
        tax_amount=Decimal("130"),
        vat_is_recoverable=False,
    )
    assert result.total_base_quantity == Decimal("120")
    assert result.total_cost == Decimal("1180")
    assert result.unit_cost == Decimal("9.8333")


def test_a_line_with_nothing_on_it_costs_nothing():
    assert costing(charged_base_quantity=Decimal("0")).unit_cost == Decimal("0")


# --------------------------------------------------------------------------- freight
def test_freight_is_spread_in_proportion_to_line_value():
    shares = allocate_freight(Decimal("100.00"), [Decimal("600"), Decimal("400")])
    assert shares == [Decimal("60.00"), Decimal("40.00")]


def test_the_shares_always_add_back_to_the_freight_charged():
    """Rounding must not leave stock valuation permanently a paisa out."""
    shares = allocate_freight(Decimal("100.00"), [Decimal("1"), Decimal("1"), Decimal("1")])
    assert sum(shares) == Decimal("100.00")
    assert shares[-1] != shares[0]  # the last line absorbs the difference


def test_no_freight_means_no_shares():
    assert allocate_freight(Decimal("0"), [Decimal("100")]) == [Decimal("0.00")]


def test_free_lines_do_not_break_the_allocation():
    assert allocate_freight(Decimal("50"), [Decimal("0"), Decimal("0")]) == [
        Decimal("0.00"),
        Decimal("0.00"),
    ]


@pytest.mark.parametrize("freight", ["10.00", "33.33", "0.01", "9999.99"])
def test_allocation_adds_up_for_any_amount(freight):
    shares = allocate_freight(Decimal(freight), [Decimal("7"), Decimal("11"), Decimal("13")])
    assert sum(shares) == Decimal(freight)
