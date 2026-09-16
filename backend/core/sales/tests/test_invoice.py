"""Selling at the counter: stock out, tax worked back out of the price, invoice numbered."""

from decimal import Decimal

import pytest

from core.inventory.models import Batch, MovementType, StockLedgerEntry
from core.inventory.services import on_hand_quantity
from core.sales.models import InvoiceStatus, SalesInvoice, SalesInvoiceLineBatch
from core.sales.services import (
    add_line,
    cancel_invoice,
    customers_who_received_batch,
    is_copy,
    issue_invoice,
    record_print,
    start_invoice,
)
from shared.errors import DomainError

from .conftest import TODAY, in_days, stock_up

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("calendar", "document_types", "inside_tenant"),
]


@pytest.fixture
def invoice(branch, counter):
    return start_invoice(branch=branch, location=counter, invoice_date=TODAY)


# --------------------------------------------------------------------------- selling
def test_a_sale_takes_stock_out_and_numbers_the_bill(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000)
    add_line(invoice, item=paracetamol, quantity=Decimal("2"))  # 2 strips of 10

    issued = issue_invoice(invoice)

    assert issued.invoice.status == InvoiceStatus.ISSUED
    assert issued.invoice.number.startswith("INV-")
    assert issued.invoice.fiscal_year == "2072/73"
    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("980.000")


def test_the_price_comes_from_the_printed_price_on_the_batch(invoice, paracetamol, branch, counter):
    """Two lots of the same medicine can carry different printed prices."""
    stock_up(paracetamol, branch, counter, 1000, mrp="2.50")
    line = add_line(invoice, item=paracetamol, quantity=Decimal("1"))
    # MRP is 2.50 per tablet, and a strip is ten of them.
    assert line.rate == Decimal("25.0000")


def test_selling_above_the_printed_price_is_refused(invoice, paracetamol, branch, counter):
    """Selling above MRP is an offence, so it is refused rather than warned about."""
    stock_up(paracetamol, branch, counter, 1000, mrp="2.00")
    with pytest.raises(DomainError) as caught:
        add_line(invoice, item=paracetamol, quantity=Decimal("1"), rate=Decimal("25"))
    assert caught.value.error.code == "PRICE_ABOVE_MRP"


def test_selling_below_the_printed_price_is_allowed(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000, mrp="2.00")
    line = add_line(invoice, item=paracetamol, quantity=Decimal("1"), rate=Decimal("18"))
    assert line.rate == Decimal("18.0000")


def test_an_item_with_no_printed_price_says_so(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 100, mrp="0")
    with pytest.raises(DomainError) as caught:
        add_line(invoice, item=paracetamol, quantity=Decimal("1"))
    assert caught.value.error.code == "NO_PRICE_SET"


def test_loose_tablets_can_be_sold(invoice, paracetamol, branch, counter):
    """Four tablets out of a strip, which is how a great deal of Nepali retail works."""
    stock_up(paracetamol, branch, counter, 1000, mrp="2.00")
    from core.catalog.models import UnitOfMeasure

    line = add_line(
        invoice,
        item=paracetamol,
        quantity=Decimal("4"),
        unit=UnitOfMeasure.objects.get(code="tab"),
    )
    assert line.base_quantity == Decimal("4.000")
    assert line.rate == Decimal("2.0000")


# --------------------------------------------------------------------------- tax
def test_tax_is_taken_out_of_the_shelf_price(invoice, thermometer, branch, counter):
    stock_up(thermometer, branch, counter, 10, mrp="1130.00")
    add_line(invoice, item=thermometer, quantity=Decimal("1"))
    issued = issue_invoice(invoice)

    assert issued.invoice.taxable_amount == Decimal("1000.00")
    assert issued.invoice.tax_amount == Decimal("130.00")
    assert issued.invoice.payable_amount == Decimal("1130.00")


def test_an_exempt_medicine_carries_no_tax(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000, mrp="2.00")
    add_line(invoice, item=paracetamol, quantity=Decimal("5"))
    issued = issue_invoice(invoice)

    assert issued.invoice.tax_amount == Decimal("0.00")
    assert issued.invoice.payable_amount == Decimal("100.00")


def test_the_tax_rate_is_fixed_at_the_time_of_sale(invoice, thermometer, branch, counter):
    """A rate change next year must not alter a bill already given to a customer."""
    stock_up(thermometer, branch, counter, 10, mrp="1130.00")
    line = add_line(invoice, item=thermometer, quantity=Decimal("1"))
    assert line.tax_percentage == Decimal("13.000")


def test_the_total_is_rounded_to_whole_rupees(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000, mrp="1.99")
    add_line(invoice, item=paracetamol, quantity=Decimal("3"))  # 3 strips at 19.90
    issued = issue_invoice(invoice)

    assert issued.invoice.taxable_amount == Decimal("59.70")
    assert issued.invoice.payable_amount == Decimal("60.00")
    assert issued.invoice.rounding_amount == Decimal("0.30")


def test_the_amount_is_available_in_words(invoice, paracetamol, branch, counter):
    """A tax invoice must carry the total in words."""
    stock_up(paracetamol, branch, counter, 1000, mrp="2.00")
    add_line(invoice, item=paracetamol, quantity=Decimal("5"))
    issued = issue_invoice(invoice)
    assert issued.amount_in_words == "One hundred rupees only"


# --------------------------------------------------------------------------- batches
def test_the_batch_nearest_expiry_is_sold_first(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 100, number="FAR", expiry_days=300, mrp="2.00")
    stock_up(paracetamol, branch, counter, 100, number="NEAR", expiry_days=30, mrp="2.00")

    add_line(invoice, item=paracetamol, quantity=Decimal("5"))  # 50 tablets
    issue_invoice(invoice)

    allocations = list(SalesInvoiceLineBatch.objects.select_related("batch").all())
    assert [a.batch.number for a in allocations] == ["NEAR"]


def test_one_line_can_draw_on_several_batches(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 30, number="NEAR", expiry_days=30, mrp="2.00")
    stock_up(paracetamol, branch, counter, 100, number="FAR", expiry_days=300, mrp="2.00")

    add_line(invoice, item=paracetamol, quantity=Decimal("5"))  # 50 tablets
    issue_invoice(invoice)

    allocations = list(SalesInvoiceLineBatch.objects.select_related("batch").order_by("created_at"))
    assert [(a.batch.number, a.quantity) for a in allocations] == [
        ("NEAR", Decimal("30.000")),
        ("FAR", Decimal("20.000")),
    ]


def test_the_cost_of_each_batch_is_captured_at_the_time(invoice, paracetamol, branch, counter):
    """So margin survives a later cost change on the same batch."""
    stock_up(paracetamol, branch, counter, 100, mrp="2.00", cost="1.25")
    add_line(invoice, item=paracetamol, quantity=Decimal("1"))
    issue_invoice(invoice)
    assert SalesInvoiceLineBatch.objects.get().unit_cost == Decimal("1.2500")


def test_expired_stock_is_never_sold(invoice, paracetamol, branch, counter):
    """The BRD's first target, enforced at the counter."""
    stock_up(paracetamol, branch, counter, 100, number="OLD", expiry_days=-1, mrp="2.00")
    add_line(invoice, item=paracetamol, quantity=Decimal("1"))

    with pytest.raises(DomainError) as caught:
        issue_invoice(invoice)
    assert caught.value.error.code == "INSUFFICIENT_STOCK"


def test_a_failed_sale_consumes_no_invoice_number(invoice, paracetamol, branch, counter):
    """The run has to stay gapless, so a bill that cannot be issued must not take a number."""
    from kernel.numbering.services import preview_next

    stock_up(paracetamol, branch, counter, 5, mrp="2.00")
    add_line(invoice, item=paracetamol, quantity=Decimal("10"))  # 100 tablets, only 5 in stock

    before = preview_next(document_type="sales.invoice", branch=branch, on_date=TODAY)
    with pytest.raises(DomainError):
        issue_invoice(invoice)
    assert preview_next(document_type="sales.invoice", branch=branch, on_date=TODAY) == before


# --------------------------------------------------------------------------- the document
def test_a_draft_moves_no_stock(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000, mrp="2.00")
    add_line(invoice, item=paracetamol, quantity=Decimal("2"))
    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("1000.000")


def test_an_empty_bill_cannot_be_issued(invoice):
    with pytest.raises(DomainError) as caught:
        issue_invoice(invoice)
    assert caught.value.error.code == "INVOICE_HAS_NO_LINES"


def test_an_issued_invoice_cannot_be_changed(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000, mrp="2.00")
    add_line(invoice, item=paracetamol, quantity=Decimal("1"))
    issue_invoice(invoice)

    with pytest.raises(DomainError) as caught:
        add_line(invoice, item=paracetamol, quantity=Decimal("1"))
    assert caught.value.error.code == "INVOICE_NOT_EDITABLE"


def test_every_stock_movement_carries_the_invoice_number(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000, mrp="2.00")
    add_line(invoice, item=paracetamol, quantity=Decimal("1"))
    issued = issue_invoice(invoice)

    entry = StockLedgerEntry.objects.get(movement_type=MovementType.SALE)
    assert entry.document_number == issued.invoice.number
    assert entry.document_type == "sales.invoice"


def test_reprints_are_counted_so_copies_can_be_marked(invoice, paracetamol, branch, counter):
    """An unmarked second original is how one sale becomes two records."""
    stock_up(paracetamol, branch, counter, 1000, mrp="2.00")
    add_line(invoice, item=paracetamol, quantity=Decimal("1"))
    issue_invoice(invoice)

    assert record_print(invoice) == 1
    assert not is_copy(invoice)
    assert record_print(invoice) == 2
    assert is_copy(invoice)


# --------------------------------------------------------------------------- cancelling
def test_cancelling_puts_the_stock_back_and_keeps_the_number(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000, mrp="2.00")
    add_line(invoice, item=paracetamol, quantity=Decimal("2"))
    issued = issue_invoice(invoice)
    number = issued.invoice.number

    cancel_invoice(invoice, reason="Customer changed their mind")

    invoice.refresh_from_db()
    assert invoice.status == InvoiceStatus.CANCELLED
    assert invoice.number == number  # a vanished bill is a gap in the run
    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("1000.000")


def test_a_draft_cannot_be_cancelled(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000, mrp="2.00")
    add_line(invoice, item=paracetamol, quantity=Decimal("1"))
    with pytest.raises(DomainError):
        cancel_invoice(invoice, reason="not issued yet")


# --------------------------------------------------------------------------- recall
def test_who_received_a_batch_can_be_answered(invoice, paracetamol, branch, counter, customer):
    """The question a recall asks, and the reason allocations are recorded."""
    stock_up(paracetamol, branch, counter, 100, number="SUSPECT", mrp="2.00")
    invoice.customer = customer
    invoice.customer_name = customer.name
    invoice.customer_phone = customer.phone
    invoice.save(update_fields=["customer", "customer_name", "customer_phone"])

    add_line(invoice, item=paracetamol, quantity=Decimal("1"))
    issue_invoice(invoice)

    affected = customers_who_received_batch(Batch.objects.get(number="SUSPECT"))
    assert [item.customer_phone for item in affected] == ["+9779812345678"]


def test_a_cancelled_sale_is_not_reported_as_a_recipient(invoice, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 100, number="SUSPECT", mrp="2.00")
    add_line(invoice, item=paracetamol, quantity=Decimal("1"))
    issue_invoice(invoice)
    cancel_invoice(invoice, reason="Returned immediately")

    assert customers_who_received_batch(Batch.objects.get(number="SUSPECT")) == []


# --------------------------------------------------------------------------- isolation
def test_invoices_do_not_leak_between_pharmacies(invoice, paracetamol, branch, counter):
    from kernel.tenancy.context import tenant_context
    from kernel.tenancy.tests.factories import make_tenant

    stock_up(paracetamol, branch, counter, 1000, mrp="2.00")
    add_line(invoice, item=paracetamol, quantity=Decimal("1"))
    issue_invoice(invoice)

    other = make_tenant("bravo")
    with tenant_context(other.tenant.id):
        assert SalesInvoice.objects.count() == 0
        assert SalesInvoiceLineBatch.objects.count() == 0


def test_stock_dated_in_the_next_fiscal_year_gets_that_years_number(branch, counter, paracetamol):
    stock_up(paracetamol, branch, counter, 1000, mrp="2.00", expiry_days=800)
    later = start_invoice(branch=branch, location=counter, invoice_date=in_days(400))
    add_line(later, item=paracetamol, quantity=Decimal("1"))
    issued = issue_invoice(later)
    assert issued.invoice.fiscal_year == "2073/74"
