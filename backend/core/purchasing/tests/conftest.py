from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest

from core.catalog.models import UnitOfMeasure
from core.catalog.services import add_pack, create_item
from core.parties.models import Party
from core.tax.models import TaxCategory
from kernel.numbering import registry
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Location
from kernel.tenancy.tests.factories import make_tenant

TODAY = date(2015, 7, 20)  # inside the synthetic calendar's range


@pytest.fixture
def _document_types() -> Iterator[None]:
    """Register the GRN document type, as core.purchasing.document_types does at startup."""
    saved = dict(registry._registry)
    if not registry.exists("purchasing.goods_receipt"):
        registry.register(
            "purchasing.goods_receipt",
            "Goods received note",
            "सामान प्राप्ति नोट",
            abbreviation="GRN",
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
def _inside_tenant(provisioned) -> Iterator[None]:
    with tenant_context(provisioned.tenant.id):
        yield


@pytest.fixture
def branch(provisioned):
    return provisioned.branch


@pytest.fixture
def store(branch):
    return Location.objects.get(branch=branch, code="STORE")


@pytest.fixture
def supplier():
    return Party.objects.create(
        name="Himalayan Distributors",
        is_supplier=True,
        pan="301234567",
        is_vat_registered=True,
    )


@pytest.fixture
def paracetamol():
    """Bought in boxes of 100 tablets, the usual shape."""
    item = create_item(
        code="PARA-500",
        name="Paracetamol 500mg",
        base_unit=UnitOfMeasure.objects.get(code="tab"),
        tax_category=TaxCategory.objects.get(code="vat-exempt"),
    )
    add_pack(item, UnitOfMeasure.objects.get(code="strip"), Decimal("10"))
    add_pack(item, UnitOfMeasure.objects.get(code="box"), Decimal("100"), is_purchase_default=True)
    return item


@pytest.fixture
def thermometer():
    """Standard-rated and not batch-tracked, so VAT recoverability shows up plainly in the cost."""
    return create_item(
        code="THERM-01",
        name="Digital thermometer",
        base_unit=UnitOfMeasure.objects.get(code="pcs"),
        tax_category=TaxCategory.objects.get(code="vat-standard"),
        item_type="device",
        is_batch_tracked=False,
        is_expiry_tracked=False,
    )


def in_days(days: int) -> date:
    return TODAY + timedelta(days=days)
