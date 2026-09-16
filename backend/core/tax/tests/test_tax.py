from datetime import date
from decimal import Decimal

import pytest

from core.tax.models import TaxCategory, TaxRate, TaxTreatment
from core.tax.services import STANDARD_VAT_PERCENTAGE, sync_tax_categories, tax_on

pytestmark = pytest.mark.django_db


@pytest.fixture
def standard():
    return TaxCategory.objects.get(code="vat-standard")


@pytest.fixture
def exempt():
    return TaxCategory.objects.get(code="vat-exempt")


def test_the_categories_the_law_defines_are_seeded():
    codes = set(TaxCategory.objects.values_list("code", flat=True))
    assert {"vat-standard", "vat-exempt", "vat-zero"} <= codes


def test_seeding_is_idempotent():
    before = (TaxCategory.objects.count(), TaxRate.objects.count())
    sync_tax_categories()
    assert (TaxCategory.objects.count(), TaxRate.objects.count()) == before


def test_exempt_and_zero_rated_are_kept_apart():
    """Both charge nothing, but they are not the same thing on a VAT return."""
    assert TaxCategory.objects.get(code="vat-exempt").treatment == TaxTreatment.EXEMPT
    assert TaxCategory.objects.get(code="vat-zero").treatment == TaxTreatment.ZERO_RATED


def test_the_exempt_category_says_to_check_the_act(exempt):
    """Nothing here decides whether medicines are exempt; that is CR-IRD-01."""
    assert "CR-IRD-01" in exempt.guidance


def test_the_standard_rate_is_thirteen_percent(standard):
    assert standard.rate_on(date(2026, 9, 16)) == STANDARD_VAT_PERCENTAGE


def test_a_rate_before_vat_existed_is_zero(standard):
    assert standard.rate_on(date(1990, 1, 1)) == Decimal("0")


def test_the_rate_in_force_on_a_date_is_used(standard):
    """A credit note against an old invoice has to use that invoice's rate."""
    TaxRate.objects.filter(category=standard).update(effective_to=date(2026, 7, 15))
    TaxRate.objects.create(
        category=standard, percentage=Decimal("15"), effective_from=date(2026, 7, 16)
    )
    assert standard.rate_on(date(2026, 7, 15)) == Decimal("13")
    assert standard.rate_on(date(2026, 7, 16)) == Decimal("15")


# --------------------------------------------------------------------------- calculation
def test_tax_is_added_on_top(standard):
    amounts = tax_on(Decimal("1000"), standard, on_date=date(2026, 9, 16))
    assert amounts.taxable == Decimal("1000.00")
    assert amounts.tax == Decimal("130.00")
    assert amounts.total == Decimal("1130.00")


def test_an_exempt_item_is_not_taxed(exempt):
    amounts = tax_on(Decimal("1000"), exempt, on_date=date(2026, 9, 16))
    assert amounts.tax == Decimal("0.00")
    assert amounts.total == Decimal("1000.00")
    assert amounts.percentage == Decimal("0")


def test_a_tax_inclusive_price_is_worked_backwards(standard):
    """A counter that prices in round rupees has the tax inside the shelf price."""
    amounts = tax_on(Decimal("113"), standard, on_date=date(2026, 9, 16), inclusive=True)
    assert amounts.taxable == Decimal("100.00")
    assert amounts.tax == Decimal("13.00")
    assert amounts.total == Decimal("113.00")


def test_the_parts_always_add_up(standard):
    """Rounding must never leave a total that does not equal its parts."""
    for amount in ("0.01", "3.33", "99.99", "1234.56", "7.77"):
        for inclusive in (False, True):
            amounts = tax_on(
                Decimal(amount), standard, on_date=date(2026, 9, 16), inclusive=inclusive
            )
            assert amounts.taxable + amounts.tax == amounts.total
