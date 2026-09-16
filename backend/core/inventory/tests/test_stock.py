"""Stock movement, FEFO allocation, and the expiry rule the BRD is measured on."""

from decimal import Decimal

import pytest
from django.db import DatabaseError, transaction

from core.inventory.models import (
    Batch,
    BatchStatus,
    MovementType,
    StockBalance,
    StockLedgerEntry,
)
from core.inventory.services import (
    allocate_fefo,
    available_quantity,
    batches_expiring_within,
    expire_batches,
    issue_stock,
    on_hand_quantity,
    post_movement,
    receive_stock,
    reconcile,
    reverse_movement,
)
from shared.errors import DomainError

from .conftest import TODAY, in_days

pytestmark = pytest.mark.django_db


def receive(item, branch, location, quantity, *, number, expiry_days=365, cost="1.00"):
    return receive_stock(
        item=item,
        branch=branch,
        location=location,
        quantity=quantity,
        batch_number=number,
        expiry_date=in_days(expiry_days),
        unit_cost=Decimal(cost),
        occurred_on=TODAY,
    )


# --------------------------------------------------------------------------- receiving
def test_receiving_creates_the_batch_and_the_stock(paracetamol, branch, store):
    entry, batch = receive(paracetamol, branch, store, 100, number="B1")

    assert batch is not None
    assert batch.number == "B1"
    assert entry.quantity == Decimal("100.000")
    assert entry.movement_type == MovementType.RECEIPT
    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("100.000")


def test_receiving_the_same_batch_again_adds_to_it(paracetamol, branch, store):
    receive(paracetamol, branch, store, 100, number="B1")
    _entry, batch = receive(paracetamol, branch, store, 50, number="B1")

    assert Batch.objects.filter(item=paracetamol).count() == 1
    assert StockBalance.objects.get(item=paracetamol, batch=batch).quantity == Decimal("150.000")


def test_a_batch_tracked_item_needs_a_batch_number(paracetamol, branch, store):
    with pytest.raises(ValueError, match="batch number is required"):
        receive_stock(
            item=paracetamol, branch=branch, location=store, quantity=10, occurred_on=TODAY
        )


def test_an_expiry_tracked_item_needs_an_expiry_date(paracetamol, branch, store):
    with pytest.raises(ValueError, match="expiry date is required"):
        receive_stock(
            item=paracetamol,
            branch=branch,
            location=store,
            quantity=10,
            batch_number="B1",
            occurred_on=TODAY,
        )


def test_stock_without_batches_is_handled_too(bandage, branch, store):
    receive_stock(item=bandage, branch=branch, location=store, quantity=24, occurred_on=TODAY)
    assert on_hand_quantity(item=bandage, branch=branch) == Decimal("24.000")
    assert Batch.objects.filter(item=bandage).count() == 0


# --------------------------------------------------------------------------- FEFO
def test_the_batch_expiring_soonest_goes_first(paracetamol, branch, store):
    """Not the one that arrived first — what matters is what goes out of date soonest."""
    receive(paracetamol, branch, store, 100, number="ARRIVED-FIRST", expiry_days=300)
    receive(paracetamol, branch, store, 100, number="EXPIRES-FIRST", expiry_days=30)

    allocations = allocate_fefo(item=paracetamol, branch=branch, quantity=50, on_date=TODAY)
    assert [a.batch.number for a in allocations] == ["EXPIRES-FIRST"]


def test_an_issue_spills_over_into_the_next_batch(paracetamol, branch, store):
    receive(paracetamol, branch, store, 40, number="NEAR", expiry_days=30)
    receive(paracetamol, branch, store, 100, number="FAR", expiry_days=300)

    allocations = allocate_fefo(item=paracetamol, branch=branch, quantity=60, on_date=TODAY)
    assert [(a.batch.number, a.quantity) for a in allocations] == [
        ("NEAR", Decimal("40.000")),
        ("FAR", Decimal("20.000")),
    ]


def test_expired_stock_is_never_allocated(paracetamol, branch, store):
    """The BRD's first target is zero expired sales, so this is a hard stop."""
    receive(paracetamol, branch, store, 100, number="EXPIRED", expiry_days=-1)
    receive(paracetamol, branch, store, 100, number="GOOD", expiry_days=200)

    allocations = allocate_fefo(item=paracetamol, branch=branch, quantity=50, on_date=TODAY)
    assert [a.batch.number for a in allocations] == ["GOOD"]


def test_stock_is_usable_up_to_and_including_its_expiry_date(paracetamol, branch, store):
    """A pack marked EXP 09/2026 may be sold on 30 September 2026, not until the 29th."""
    _entry, batch = receive(paracetamol, branch, store, 10, number="TODAY", expiry_days=0)
    assert batch.is_sellable_on(TODAY)
    assert not batch.is_sellable_on(in_days(1))


def test_quarantined_stock_is_not_allocated(paracetamol, branch, store):
    _entry, held = receive(paracetamol, branch, store, 100, number="HELD", expiry_days=200)
    held.status = BatchStatus.QUARANTINED
    held.save(update_fields=["status"])
    receive(paracetamol, branch, store, 10, number="FREE", expiry_days=300)

    allocations = allocate_fefo(item=paracetamol, branch=branch, quantity=10, on_date=TODAY)
    assert [a.batch.number for a in allocations] == ["FREE"]


def test_running_out_says_how_much_there_was(paracetamol, branch, store):
    receive(paracetamol, branch, store, 30, number="B1")
    with pytest.raises(DomainError) as caught:
        allocate_fefo(item=paracetamol, branch=branch, quantity=50, on_date=TODAY)

    assert caught.value.error.code == "INSUFFICIENT_STOCK"
    assert "30.000 available" in caught.value.message


def test_available_ignores_expired_stock_but_on_hand_does_not(paracetamol, branch, store):
    receive(paracetamol, branch, store, 100, number="EXPIRED", expiry_days=-1)
    receive(paracetamol, branch, store, 40, number="GOOD", expiry_days=200)

    assert available_quantity(item=paracetamol, branch=branch, on_date=TODAY) == Decimal("40.000")
    # A physical count would still find 140 on the shelf.
    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("140.000")


# --------------------------------------------------------------------------- issuing
def test_issuing_reduces_stock_and_records_each_batch(paracetamol, branch, store):
    receive(paracetamol, branch, store, 40, number="NEAR", expiry_days=30, cost="2.00")
    receive(paracetamol, branch, store, 100, number="FAR", expiry_days=300, cost="3.00")

    entries = issue_stock(
        item=paracetamol,
        branch=branch,
        quantity=60,
        occurred_on=TODAY,
        document_type="sales.invoice",
        document_number="INV-001",
    )

    assert [entry.quantity for entry in entries] == [Decimal("-40.000"), Decimal("-20.000")]
    # Cost follows the batch, so margin is right even when two lots cost different amounts.
    assert [entry.unit_cost for entry in entries] == [Decimal("2.0000"), Decimal("3.0000")]
    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("80.000")
    assert all(entry.document_number == "INV-001" for entry in entries)


def test_selling_an_expired_batch_directly_is_refused(paracetamol, branch, store):
    """FEFO would never pick it, but a caller naming the batch must still be stopped."""
    _entry, batch = receive(paracetamol, branch, store, 10, number="OLD", expiry_days=-1)
    with pytest.raises(DomainError) as caught:
        post_movement(
            item=paracetamol,
            branch=branch,
            location=store,
            batch=batch,
            quantity=-1,
            movement_type=MovementType.SALE,
            occurred_on=TODAY,
        )
    assert caught.value.error.code == "EXPIRED_BATCH"


def test_expired_stock_can_still_be_written_off(paracetamol, branch, store):
    """It has to be able to leave the shelf, or it would be stuck there forever."""
    _entry, batch = receive(paracetamol, branch, store, 10, number="OLD", expiry_days=-1)
    entry = post_movement(
        item=paracetamol,
        branch=branch,
        location=store,
        batch=batch,
        quantity=-10,
        movement_type=MovementType.WRITE_OFF,
        occurred_on=TODAY,
        note="Expired",
    )
    assert entry.quantity == Decimal("-10.000")
    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("0.000")


def test_stock_cannot_go_negative_by_default(paracetamol, branch, store):
    receive(paracetamol, branch, store, 5, number="B1")
    with pytest.raises(DomainError) as caught:
        post_movement(
            item=paracetamol,
            branch=branch,
            location=store,
            batch=Batch.objects.get(number="B1"),
            quantity=-10,
            movement_type=MovementType.SALE,
            occurred_on=TODAY,
        )
    assert caught.value.error.code == "INSUFFICIENT_STOCK"


def test_negative_stock_can_be_allowed_deliberately(paracetamol, branch, store):
    """Offline counters can sell what the server has not been told about yet."""
    receive(paracetamol, branch, store, 5, number="B1")
    post_movement(
        item=paracetamol,
        branch=branch,
        location=store,
        batch=Batch.objects.get(number="B1"),
        quantity=-10,
        movement_type=MovementType.SALE,
        occurred_on=TODAY,
        allow_negative=True,
    )
    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("-5.000")


def test_a_zero_movement_is_refused(paracetamol, branch, store):
    with pytest.raises(ValueError, match="not a movement"):
        post_movement(
            item=paracetamol,
            branch=branch,
            location=store,
            quantity=0,
            movement_type=MovementType.ADJUSTMENT,
            occurred_on=TODAY,
        )


# --------------------------------------------------------------------------- the ledger is history
def test_a_ledger_entry_cannot_be_changed(paracetamol, branch, store):
    entry, _batch = receive(paracetamol, branch, store, 10, number="B1")
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        StockLedgerEntry.objects.filter(pk=entry.pk).update(quantity=Decimal("999"))


def test_a_ledger_entry_cannot_be_deleted(paracetamol, branch, store):
    entry, _batch = receive(paracetamol, branch, store, 10, number="B1")
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        StockLedgerEntry.objects.filter(pk=entry.pk).delete()


def test_a_mistake_is_corrected_by_reversing_it(paracetamol, branch, store):
    entry, _batch = receive(paracetamol, branch, store, 100, number="B1")
    reversal = reverse_movement(entry, reason="Received against the wrong branch")

    assert reversal.quantity == Decimal("-100.000")
    assert reversal.reverses_id == entry.pk
    assert on_hand_quantity(item=paracetamol, branch=branch) == Decimal("0.000")
    # Both entries remain: the ledger shows what happened, including the correction.
    assert StockLedgerEntry.objects.count() == 2


# --------------------------------------------------------------------------- expiry management
def test_batches_past_their_date_are_marked_expired(paracetamol, branch, store):
    receive(paracetamol, branch, store, 10, number="OLD", expiry_days=-1)
    receive(paracetamol, branch, store, 10, number="GOOD", expiry_days=10)

    assert expire_batches(on_date=TODAY) == 1
    assert Batch.objects.get(number="OLD").status == BatchStatus.EXPIRED
    assert Batch.objects.get(number="GOOD").status == BatchStatus.AVAILABLE


def test_stock_about_to_expire_can_be_found_in_time(paracetamol, branch, store):
    """So it can be discounted, returned or moved before it becomes a loss."""
    receive(paracetamol, branch, store, 10, number="SOON", expiry_days=20)
    receive(paracetamol, branch, store, 10, number="LATER", expiry_days=200)

    soon = batches_expiring_within(days=30, branch=branch, on_date=TODAY)
    assert [batch.number for batch in soon] == ["SOON"]


def test_already_expired_stock_is_not_reported_as_expiring_soon(paracetamol, branch, store):
    receive(paracetamol, branch, store, 10, number="GONE", expiry_days=-5)
    assert batches_expiring_within(days=30, branch=branch, on_date=TODAY) == []


# --------------------------------------------------------------------------- reconciliation
def test_balances_agree_with_the_ledger(paracetamol, bandage, branch, store, counter):
    receive(paracetamol, branch, store, 100, number="B1")
    receive(paracetamol, branch, counter, 20, number="B1")
    receive_stock(item=bandage, branch=branch, location=store, quantity=12, occurred_on=TODAY)
    issue_stock(item=paracetamol, branch=branch, quantity=30, occurred_on=TODAY)

    assert reconcile() == []


def test_a_balance_written_outside_the_service_layer_is_reported(paracetamol, branch, store):
    """Reported, not silently corrected: the number being wrong is the symptom, not the problem."""
    receive(paracetamol, branch, store, 100, number="B1")
    balance = StockBalance.objects.get(item=paracetamol)
    balance.quantity = Decimal("999.000")
    balance.save(update_fields=["quantity"])

    discrepancies = reconcile()
    assert len(discrepancies) == 1
    assert discrepancies[0].balance == Decimal("999.000")
    assert discrepancies[0].ledger == Decimal("100.000")
    assert discrepancies[0].difference == Decimal("899.000")


# --------------------------------------------------------------------------- isolation
def test_stock_does_not_leak_between_pharmacies(paracetamol, branch, store):
    from kernel.tenancy.context import tenant_context
    from kernel.tenancy.tests.factories import make_tenant

    receive(paracetamol, branch, store, 100, number="B1")

    other = make_tenant("bravo")
    with tenant_context(other.tenant.id):
        assert StockLedgerEntry.objects.count() == 0
        assert StockBalance.objects.count() == 0
        assert Batch.objects.count() == 0
