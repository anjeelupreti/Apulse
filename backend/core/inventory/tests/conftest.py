from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest

from core.catalog.models import Item, UnitOfMeasure
from core.catalog.services import add_pack, create_item
from core.tax.models import TaxCategory
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Location
from kernel.tenancy.tests.factories import make_tenant

TODAY = date(2026, 9, 16)


@pytest.fixture
def provisioned():
    return make_tenant("alpha")


@pytest.fixture(autouse=True)
def _inside_tenant(provisioned) -> Iterator[None]:
    with tenant_context(provisioned.tenant.id):
        yield


@pytest.fixture
def branch(provisioned):
    return provisioned.branch


@pytest.fixture
def counter(branch) -> Location:
    return Location.objects.get(branch=branch, code="COUNTER")


@pytest.fixture
def store(branch) -> Location:
    return Location.objects.get(branch=branch, code="STORE")


@pytest.fixture
def paracetamol() -> Item:
    return create_item(
        code="PARA-500",
        name="Paracetamol 500mg",
        base_unit=UnitOfMeasure.objects.get(code="tab"),
        tax_category=TaxCategory.objects.get(code="vat-exempt"),
    )


@pytest.fixture
def bandage() -> Item:
    """Not tracked by batch or expiry — plenty of pharmacy stock is not."""
    item = create_item(
        code="BAND-01",
        name="Gauze bandage",
        base_unit=UnitOfMeasure.objects.get(code="pcs"),
        tax_category=TaxCategory.objects.get(code="vat-standard"),
        is_batch_tracked=False,
        is_expiry_tracked=False,
    )
    add_pack(item, UnitOfMeasure.objects.get(code="box"), Decimal("12"))
    return item


def in_days(days: int) -> date:
    return TODAY + timedelta(days=days)
