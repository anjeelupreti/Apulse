from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest

from core.catalog.models import UnitOfMeasure
from core.catalog.services import add_pack, create_item
from core.inventory.services import receive_stock
from core.payments.models import PaymentMode
from core.payments.services import install_default_modes, open_shift
from core.tax.models import TaxCategory
from kernel.identity.models import User
from kernel.numbering import registry
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Location
from kernel.tenancy.tests.factories import make_tenant

TODAY = date(2015, 7, 20)  # inside the synthetic calendar's range


@pytest.fixture
def document_types() -> Iterator[None]:
    saved = dict(registry._registry)
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
def modes(inside_tenant):
    install_default_modes()
    return {mode.code: mode for mode in PaymentMode.objects.all()}


@pytest.fixture
def cash(modes):
    return modes["cash"]


@pytest.fixture
def fonepay(modes):
    return modes["fonepay"]


@pytest.fixture
def on_account(modes):
    return modes["credit"]


@pytest.fixture
def cashier():
    return User.objects.create_user("till@example.com", "s3cure-pass-phrase", full_name="Gita Rai")


@pytest.fixture
def supervisor():
    return User.objects.create_user(
        "boss@example.com", "s3cure-pass-phrase", full_name="Hari Thapa"
    )


@pytest.fixture
def shift(branch, counter, cashier):
    return open_shift(
        branch=branch,
        location=counter,
        cashier=cashier,
        opening_float=Decimal("2000"),
        business_date=TODAY,
    )


@pytest.fixture
def paracetamol():
    item = create_item(
        code="PARA-500",
        name="Paracetamol 500mg",
        base_unit=UnitOfMeasure.objects.get(code="tab"),
        tax_category=TaxCategory.objects.get(code="vat-exempt"),
        mrp=Decimal("2.00"),
    )
    add_pack(item, UnitOfMeasure.objects.get(code="strip"), Decimal("10"), is_sale_default=True)
    return item


def stock_up(item, branch, location, quantity=1000):
    return receive_stock(
        item=item,
        branch=branch,
        location=location,
        quantity=Decimal(str(quantity)),
        batch_number="B1",
        expiry_date=TODAY + timedelta(days=365),
        mrp=Decimal("2.00"),
        unit_cost=Decimal("1.00"),
        occurred_on=TODAY,
    )
