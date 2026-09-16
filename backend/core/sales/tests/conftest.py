from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest

from core.catalog.models import UnitOfMeasure
from core.catalog.services import add_pack, create_item
from core.inventory.services import receive_stock
from core.parties.models import Party
from core.tax.models import TaxCategory
from kernel.numbering import registry
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Location
from kernel.tenancy.tests.factories import make_tenant

TODAY = date(2015, 7, 20)  # inside the synthetic calendar's range


@pytest.fixture
def document_types() -> Iterator[None]:
    saved = dict(registry._registry)
    if not registry.exists("sales.invoice"):
        registry.register(
            "sales.invoice", "Tax invoice", "कर बीजक", abbreviation="INV", is_tax_document=True
        )
    try:
        yield
    finally:
        registry._registry.clear()
        registry._registry.update(saved)


@pytest.fixture
def provisioned():
    return make_tenant("alpha")


@pytest.fixture
def inside_tenant(provisioned) -> Iterator[None]:
    with tenant_context(provisioned.tenant.id):
        yield


@pytest.fixture
def branch(provisioned):
    return provisioned.branch


@pytest.fixture
def counter(branch):
    return Location.objects.get(branch=branch, code="COUNTER")


@pytest.fixture
def customer():
    return Party.objects.create(name="Sita Sharma", is_customer=True, phone="+9779812345678")


@pytest.fixture
def paracetamol():
    """Exempt medicine, sold loose or by the strip."""
    item = create_item(
        code="PARA-500",
        name="Paracetamol 500mg",
        base_unit=UnitOfMeasure.objects.get(code="tab"),
        tax_category=TaxCategory.objects.get(code="vat-exempt"),
    )
    add_pack(item, UnitOfMeasure.objects.get(code="strip"), Decimal("10"), is_sale_default=True)
    return item


@pytest.fixture
def thermometer():
    """Standard-rated and not batch-tracked, so it prices from the item rather than a batch."""
    return create_item(
        code="THERM-01",
        name="Digital thermometer",
        base_unit=UnitOfMeasure.objects.get(code="pcs"),
        tax_category=TaxCategory.objects.get(code="vat-standard"),
        item_type="device",
        is_batch_tracked=False,
        is_expiry_tracked=False,
        mrp=Decimal("1130.00"),
    )


def stock_up(
    item, branch, location, quantity, *, number="B1", expiry_days=365, mrp="2.00", cost="1.00"
):
    """Put stock on the shelf with a printed price."""
    return receive_stock(
        item=item,
        branch=branch,
        location=location,
        quantity=Decimal(str(quantity)),
        batch_number=number if item.is_batch_tracked else "",
        expiry_date=TODAY + timedelta(days=expiry_days) if item.is_expiry_tracked else None,
        mrp=Decimal(mrp),
        unit_cost=Decimal(cost),
        occurred_on=TODAY,
    )


def in_days(days: int) -> date:
    return TODAY + timedelta(days=days)
