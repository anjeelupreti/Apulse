from decimal import Decimal

import pytest

from core.catalog.models import Item, UnitOfMeasure
from core.catalog.services import add_pack, create_item
from core.tax.models import TaxCategory
from kernel.tenancy.tests.factories import make_tenant


@pytest.fixture
def provisioned():
    return make_tenant("alpha")


@pytest.fixture
def exempt_category():
    return TaxCategory.objects.get(code="vat-exempt")


@pytest.fixture
def units():
    return {unit.code: unit for unit in UnitOfMeasure.objects.all()}


@pytest.fixture
def paracetamol(units, exempt_category) -> Item:
    """A tablet sold loose, in strips of 10 and in boxes of 100 — the common shape in Nepal."""
    item = create_item(
        code="PARA-500",
        name="Paracetamol 500mg",
        base_unit=units["tab"],
        tax_category=exempt_category,
    )
    add_pack(item, units["strip"], Decimal("10"))
    add_pack(item, units["box"], Decimal("100"), is_purchase_default=True)
    return item
