"""Seeding tax categories, and working out the tax on a line."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction

from shared.formatting import quantize_money

from .models import TaxCategory, TaxRate, TaxTreatment

#: Nepal's standard VAT rate. The rate itself is not in doubt; **which goods it applies to is**
#: (CR-IRD-01), which is why no item is given a category by default.
STANDARD_VAT_PERCENTAGE = Decimal("13")
#: VAT Act 2052 came into force on this date. Rates are dated from here so an old document can
#: always be re-priced with the rate it actually carried.
VAT_START = date(1997, 11, 16)

SEED_CATEGORIES: tuple[dict[str, Any], ...] = (
    {
        "code": "vat-standard",
        "name": "VAT 13%",
        "name_ne": "मू.अ.कर १३%",
        "treatment": TaxTreatment.STANDARD,
        "description": "Standard-rated goods and services.",
        "guidance": "Cosmetics, supplements, devices and general goods are normally taxable.",
        "percentage": STANDARD_VAT_PERCENTAGE,
    },
    {
        "code": "vat-exempt",
        "name": "VAT exempt",
        "name_ne": "मू.अ.कर छुट",
        "treatment": TaxTreatment.EXEMPT,
        "description": "Goods listed as exempt under the VAT Act.",
        "guidance": "Most medicines are expected to fall here. Confirm against the VAT Act "
        "schedule before classifying stock (CR-IRD-01).",
        "percentage": Decimal("0"),
    },
    {
        "code": "vat-zero",
        "name": "Zero-rated",
        "name_ne": "शून्य दर",
        "treatment": TaxTreatment.ZERO_RATED,
        "description": "Taxable at 0%, typically exports.",
        "guidance": "Zero-rated is not the same as exempt; it is taxable at zero.",
        "percentage": Decimal("0"),
    },
)


@transaction.atomic
def sync_tax_categories() -> int:
    """Create the categories the law defines. Existing rates are never rewritten."""
    for seed in SEED_CATEGORIES:
        category, _ = TaxCategory.objects.update_or_create(
            code=seed["code"],
            defaults={
                "name": seed["name"],
                "name_ne": seed["name_ne"],
                "treatment": seed["treatment"],
                "description": seed["description"],
                "guidance": seed["guidance"],
            },
        )
        TaxRate.objects.get_or_create(
            category=category,
            effective_from=VAT_START,
            defaults={"percentage": seed["percentage"], "note": "Seeded with the category"},
        )
    return len(SEED_CATEGORIES)


@dataclass(frozen=True, slots=True)
class TaxAmounts:
    taxable: Decimal
    tax: Decimal
    total: Decimal
    percentage: Decimal


def tax_on(
    amount: Decimal, category: TaxCategory, *, on_date: date, inclusive: bool = False
) -> TaxAmounts:
    """Split an amount into its taxable part and its tax.

    `inclusive` is for a counter that prices in round rupees: the shelf price already contains the
    tax and has to be worked backwards, rather than having tax added on top.
    """
    percentage = category.rate_on(on_date)
    if percentage == 0:
        taxable = quantize_money(amount)
        return TaxAmounts(
            taxable=taxable, tax=Decimal("0.00"), total=taxable, percentage=percentage
        )

    if inclusive:
        taxable = quantize_money(amount / (1 + percentage / 100))
        tax = quantize_money(amount) - taxable
        return TaxAmounts(
            taxable=taxable, tax=tax, total=quantize_money(amount), percentage=percentage
        )

    taxable = quantize_money(amount)
    tax = quantize_money(taxable * percentage / 100)
    return TaxAmounts(taxable=taxable, tax=tax, total=taxable + tax, percentage=percentage)
