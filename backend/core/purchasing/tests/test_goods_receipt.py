"""Receiving a delivery: where stock, batches, expiry and cost all enter the system."""

from decimal import Decimal

import pytest

from core.inventory.models import Batch, MovementType, StockLedgerEntry
from core.inventory.services import on_hand_quantity
from core.purchasing.models import GoodsReceipt, ReceiptStatus
from core.purchasing.services import (
    add_line,
    cancel_receipt,
    post_receipt,
    start_receipt,
)
from shared.errors import DomainError

from .conftest import TODAY, in_days

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("calendar", "_document_types", "_inside_tenant"),
]


@pytest.fixture
def receipt(branch, store, supplier):
    return start_receipt(
        branch=branch,
        location=store,
        supplier=supplier,
        supplier_invoice_number="SUP-9001",
        supplier_invoice_date=TODAY,
        received_on=TODAY,
    )


def add_paracetamol(receipt, paracetamol, **overrides):
    defaults = {
        "item": paracetamol,
        "quantity": Decimal("10"),  # 10 boxes of 100 = 1000 tablets
        "rate": Decimal("500"),
        "batch_number": "B-2082-01",
        "expiry_date": in_days(400),
        "mrp": Decimal("800"),
    }
    return add_line(receipt, **{**defaults, **overrides})


# --------------------------------------------------------------------------- posting
def test_posting_brings_stock_in_and_numbers_the_document(receipt, paracetamol, branch):
    add_paracetamol(receipt, paracetamol)
    posted = post_receipt(receipt)

    assert posted.receipt.status == ReceiptStatus.POSTED
    assert posted.receipt.number.startswith("GRN-")
    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("1000.000")


def test_the_batch_carries_its_expiry_and_printed_price(receipt, paracetamol):
    add_paracetamol(receipt, paracetamol)
    post_receipt(receipt)

    batch = Batch.objects.get(number="B-2082-01")
    assert batch.expiry_date == in_days(400)
    # MRP is entered per box of 100 and stored per tablet, matching how cost is held.
    assert batch.mrp == Decimal("8.0000")


def test_the_stock_movement_points_back_at_the_document(receipt, paracetamol):
    add_paracetamol(receipt, paracetamol)
    posted = post_receipt(receipt)

    entry = StockLedgerEntry.objects.get(movement_type=MovementType.RECEIPT)
    assert entry.document_type == "purchasing.goods_receipt"
    assert entry.document_id == str(receipt.pk)
    assert entry.document_number == posted.receipt.number


def test_a_draft_moves_no_stock(receipt, paracetamol, branch):
    add_paracetamol(receipt, paracetamol)
    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("0.000")


def test_an_empty_receipt_cannot_be_posted(receipt):
    with pytest.raises(DomainError) as caught:
        post_receipt(receipt)
    assert caught.value.error.code == "RECEIPT_HAS_NO_LINES"


def test_a_posted_receipt_cannot_be_changed(receipt, paracetamol):
    add_paracetamol(receipt, paracetamol)
    post_receipt(receipt)

    with pytest.raises(DomainError) as caught:
        add_paracetamol(receipt, paracetamol, batch_number="B-2")
    assert caught.value.error.code == "RECEIPT_NOT_EDITABLE"


def test_posting_twice_is_refused(receipt, paracetamol):
    add_paracetamol(receipt, paracetamol)
    post_receipt(receipt)
    with pytest.raises(DomainError):
        post_receipt(receipt)


# --------------------------------------------------------------------------- bonus quantity
def test_free_quantity_is_stock_and_lowers_the_unit_cost(receipt, paracetamol, branch):
    """'10 + 1 free' — eleven boxes arrive, ten are charged for."""
    line = add_paracetamol(receipt, paracetamol, quantity=Decimal("10"), free_quantity=Decimal("1"))
    posted = post_receipt(receipt)

    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("1100.000")
    costing = posted.costings[line.pk]
    assert costing.total_base_quantity == Decimal("1100.000")
    # 5000 for 1100 tablets, not for 1000.
    assert costing.unit_cost == Decimal("4.5455")
    assert costing.unit_cost_ignoring_bonus == Decimal("5.0000")


def test_the_batch_records_the_cost_including_the_bonus(receipt, paracetamol):
    add_paracetamol(receipt, paracetamol, quantity=Decimal("10"), free_quantity=Decimal("1"))
    post_receipt(receipt)
    assert Batch.objects.get(number="B-2082-01").cost == Decimal("4.5455")


# ------------------------------------------------------------------- discounts, freight and VAT
def test_a_discount_reduces_the_cost(receipt, paracetamol):
    line = add_paracetamol(receipt, paracetamol, discount_percent=Decimal("10"))
    posted = post_receipt(receipt)
    assert line.net_amount == Decimal("4500.00")
    assert posted.costings[line.pk].unit_cost == Decimal("4.5000")


def test_freight_is_shared_across_the_lines(branch, store, supplier, paracetamol, thermometer):
    receipt = start_receipt(
        branch=branch,
        location=store,
        supplier=supplier,
        supplier_invoice_number="SUP-FREIGHT",
        supplier_invoice_date=TODAY,
        received_on=TODAY,
        freight_amount=Decimal("300"),
    )
    first = add_paracetamol(receipt, paracetamol)  # 5000
    second = add_line(
        receipt, item=thermometer, quantity=Decimal("10"), rate=Decimal("500")
    )  # 5000
    posted = post_receipt(receipt)

    assert posted.costings[first.pk].freight_share == Decimal("150.00")
    assert posted.costings[second.pk].freight_share == Decimal("150.00")


def test_a_vat_registered_pharmacy_does_not_carry_vat_into_cost(receipt, thermometer, branch):
    """Input VAT is reclaimed, so it never formed part of what the stock cost."""
    assert branch.legal_entity.is_vat_registered is False
    branch.legal_entity.is_vat_registered = True
    branch.legal_entity.save(update_fields=["is_vat_registered"])

    line = add_line(receipt, item=thermometer, quantity=Decimal("10"), rate=Decimal("100"))
    posted = post_receipt(receipt)
    assert posted.costings[line.pk].non_recoverable_tax == Decimal("0")
    assert posted.costings[line.pk].unit_cost == Decimal("100.0000")


def test_a_pharmacy_below_the_vat_threshold_carries_vat_into_cost(receipt, thermometer):
    line = add_line(receipt, item=thermometer, quantity=Decimal("10"), rate=Decimal("100"))
    posted = post_receipt(receipt)
    # 13% on 1000, spread over 10 pieces.
    assert posted.costings[line.pk].non_recoverable_tax == Decimal("130.00")
    assert posted.costings[line.pk].unit_cost == Decimal("113.0000")


def test_an_exempt_medicine_carries_no_vat_either_way(receipt, paracetamol):
    line = add_paracetamol(receipt, paracetamol)
    posted = post_receipt(receipt)
    assert posted.costings[line.pk].non_recoverable_tax == Decimal("0")


# --------------------------------------------------------------------------- data quality
def test_the_same_supplier_invoice_cannot_be_entered_twice(branch, store, supplier):
    """Entering a delivery twice is the most common way stock gets doubled."""
    start_receipt(
        branch=branch,
        location=store,
        supplier=supplier,
        supplier_invoice_number="SUP-DUP",
        supplier_invoice_date=TODAY,
    )
    with pytest.raises(DomainError) as caught:
        start_receipt(
            branch=branch,
            location=store,
            supplier=supplier,
            supplier_invoice_number="SUP-DUP",
            supplier_invoice_date=TODAY,
        )
    assert caught.value.error.code == "SUPPLIER_INVOICE_ALREADY_ENTERED"


def test_a_batch_tracked_item_cannot_be_received_without_a_batch(receipt, paracetamol):
    add_paracetamol(receipt, paracetamol, batch_number="")
    with pytest.raises(DomainError) as caught:
        post_receipt(receipt)
    assert caught.value.error.code == "BATCH_DETAILS_REQUIRED"


def test_an_expiry_tracked_item_cannot_be_received_without_an_expiry(receipt, paracetamol):
    add_paracetamol(receipt, paracetamol, expiry_date=None)
    with pytest.raises(DomainError) as caught:
        post_receipt(receipt)
    assert caught.value.error.code == "BATCH_DETAILS_REQUIRED"


def test_already_expired_stock_is_refused_by_default(receipt, paracetamol):
    add_paracetamol(receipt, paracetamol, expiry_date=in_days(-1))
    with pytest.raises(DomainError) as caught:
        post_receipt(receipt)
    assert caught.value.error.code == "RECEIVING_EXPIRED_STOCK"


def test_expired_stock_can_be_taken_in_deliberately(receipt, paracetamol, branch):
    """Sometimes it is received only so it can be returned to the supplier."""
    add_paracetamol(receipt, paracetamol, expiry_date=in_days(-1))
    post_receipt(receipt, allow_expired=True)
    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("1000.000")


# --------------------------------------------------------------------------- cancelling
def test_cancelling_reverses_the_stock_but_keeps_the_document(receipt, paracetamol, branch):
    add_paracetamol(receipt, paracetamol)
    posted = post_receipt(receipt)
    number = posted.receipt.number

    cancel_receipt(receipt, reason="Delivery refused at the door")

    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("0.000")
    receipt.refresh_from_db()
    assert receipt.status == ReceiptStatus.CANCELLED
    # The number stays. A cancelled document that disappears is a gap in the run.
    assert receipt.number == number
    assert StockLedgerEntry.objects.filter(movement_type=MovementType.REVERSAL).count() == 1


def test_cancelling_twice_is_harmless(receipt, paracetamol):
    add_paracetamol(receipt, paracetamol)
    post_receipt(receipt)
    cancel_receipt(receipt, reason="first")
    cancel_receipt(receipt, reason="second")
    assert StockLedgerEntry.objects.filter(movement_type=MovementType.REVERSAL).count() == 1


def test_a_draft_cannot_be_cancelled(receipt, paracetamol):
    add_paracetamol(receipt, paracetamol)
    with pytest.raises(DomainError):
        cancel_receipt(receipt, reason="not posted yet")


# --------------------------------------------------------------------------- isolation
def test_receipts_do_not_leak_between_pharmacies(receipt, paracetamol):
    from kernel.tenancy.context import tenant_context
    from kernel.tenancy.tests.factories import make_tenant

    add_paracetamol(receipt, paracetamol)
    post_receipt(receipt)

    other = make_tenant("bravo")
    with tenant_context(other.tenant.id):
        assert GoodsReceipt.objects.count() == 0
