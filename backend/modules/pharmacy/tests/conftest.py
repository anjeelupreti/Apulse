from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest

from core.catalog.models import UnitOfMeasure
from core.catalog.services import add_pack, create_item
from core.inventory.services import receive_stock
from core.practitioners.models import Council, Practitioner
from core.sales.services import start_invoice
from core.tax.models import TaxCategory
from kernel.numbering import registry
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Location
from kernel.tenancy.tests.factories import make_tenant
from modules.pharmacy.models import DrugSchedule, MedicineProfile

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
def doctor():
    return Practitioner.objects.create(
        name="Dr Anjana Thapa",
        council=Council.MEDICAL,
        registration_number="NMC-12345",
        speciality="General practice",
    )


@pytest.fixture
def unregistered_doctor():
    """A name read off a prescription pad, with no legible registration number."""
    return Practitioner.objects.create(name="Dr Illegible", council=Council.MEDICAL)


def make_medicine(
    *, code: str, name: str, generic: str, schedule: str, mrp: str = "2.00"
) -> MedicineProfile:
    item = create_item(
        code=code,
        name=name,
        base_unit=UnitOfMeasure.objects.get(code="tab"),
        tax_category=TaxCategory.objects.get(code="vat-exempt"),
        mrp=Decimal(mrp),
    )
    add_pack(item, UnitOfMeasure.objects.get(code="strip"), Decimal("10"), is_sale_default=True)
    return MedicineProfile.objects.create(
        item=item,
        generic_name=generic,
        strength="500mg",
        schedule=schedule,
        is_narcotic=schedule == DrugSchedule.KA,
    )


@pytest.fixture
def paracetamol():
    """Samuha Ga — supplied on a pharmacist's advice, no prescription needed."""
    return make_medicine(
        code="PARA-500",
        name="Paracetamol 500mg",
        generic="Paracetamol",
        schedule=DrugSchedule.GA,
    )


@pytest.fixture
def amoxicillin():
    """Samuha Kha — an antibiotic, prescription required."""
    return make_medicine(
        code="AMOX-500",
        name="Amoxicillin 500mg",
        generic="Amoxicillin",
        schedule=DrugSchedule.KHA,
    )


@pytest.fixture
def morphine():
    """Samuha Ka — narcotic, prescription and a register entry."""
    return make_medicine(
        code="MORPH-10",
        name="Morphine 10mg",
        generic="Morphine",
        schedule=DrugSchedule.KA,
    )


@pytest.fixture
def unclassified():
    return make_medicine(
        code="UNK-01",
        name="Unclassified tablet",
        generic="Unknown",
        schedule=DrugSchedule.UNCLASSIFIED,
    )


def stock_up(profile: MedicineProfile, branch, location, quantity=1000):
    return receive_stock(
        item=profile.item,
        branch=branch,
        location=location,
        quantity=Decimal(str(quantity)),
        batch_number="B1",
        expiry_date=TODAY + timedelta(days=365),
        mrp=Decimal("2.00"),
        unit_cost=Decimal("1.00"),
        occurred_on=TODAY,
    )


def bill_for(profile: MedicineProfile, branch, counter, *, strips="1"):
    """A draft bill with one medicine on it."""
    from core.sales.services import add_line

    stock_up(profile, branch, counter)
    invoice = start_invoice(branch=branch, location=counter, invoice_date=TODAY)
    add_line(invoice, item=profile.item, quantity=Decimal(strips))
    return invoice
