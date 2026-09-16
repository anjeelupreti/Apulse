"""The controlled-drug register: what goes in the cabinet, what comes out, and what it says."""

from datetime import timedelta
from decimal import Decimal

import pytest

from core.purchasing.services import add_line as add_receipt_line
from core.purchasing.services import cancel_receipt, post_receipt, start_receipt
from core.sales.services import cancel_invoice, issue_invoice
from kernel.tenancy.models import Location, LocationType
from modules.pharmacy.models import (
    DrugSchedule,
    NarcoticRegisterBalance,
    NarcoticRegisterEntry,
    Prescription,
    RegisterEntryType,
)
from modules.pharmacy.register import (
    balance_of,
    correct_entry,
    reconcile_register,
    record_count,
    register_page,
    total_balance_of,
)
from modules.pharmacy.services import classify
from shared.errors import DomainError

from .conftest import TODAY, bill_for, stock_up

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("calendar", "document_types", "inside_tenant"),
]


@pytest.fixture
def cabinet(branch):
    """Provisioning creates one for every branch — narcotics are not kept on an open shelf."""
    return Location.objects.get(branch=branch, type=LocationType.LOCKED_CABINET)


def prescribe(invoice, doctor):
    return Prescription.objects.create(
        invoice=invoice,
        prescriber=doctor,
        patient_name="Ram Bahadur",
        patient_phone="9800000000",
        prescribed_on=TODAY,
    )


def sell(morphine, branch, counter, doctor, *, strips="1", actor=None):
    invoice = bill_for(morphine, branch, counter, strips=strips)
    prescribe(invoice, doctor)
    return issue_invoice(invoice, actor=actor)


# --------------------------------------------------------------------------- what gets recorded
def test_dispensing_a_narcotic_writes_a_register_line(morphine, branch, counter, doctor):
    sell(morphine, branch, counter, doctor)

    entry = NarcoticRegisterEntry.objects.get()
    assert entry.entry_type == RegisterEntryType.DISPENSED
    assert entry.quantity == Decimal("-10")  # one strip of ten tablets, leaving the cabinet
    assert entry.item == morphine.item


def test_an_antibiotic_is_not_in_the_register(amoxicillin, branch, counter, doctor):
    """Samuha Kha needs a prescription but not a register entry. Only Ka is registered."""
    invoice = bill_for(amoxicillin, branch, counter)
    prescribe(invoice, doctor)
    issue_invoice(invoice)

    assert not NarcoticRegisterEntry.objects.exists()


def test_an_over_the_counter_sale_writes_nothing(paracetamol, branch, counter):
    issue_invoice(bill_for(paracetamol, branch, counter))
    assert not NarcoticRegisterEntry.objects.exists()


def test_the_line_names_the_patient_and_the_prescriber(morphine, branch, counter, doctor):
    sell(morphine, branch, counter, doctor)

    entry = NarcoticRegisterEntry.objects.get()
    assert entry.patient_name == "Ram Bahadur"
    assert entry.prescriber == doctor
    assert entry.prescriber_name == doctor.name
    assert entry.prescriber_registration_number == "NMC-12345"
    assert entry.prescription is not None


def test_the_prescriber_name_is_kept_even_if_the_record_is_later_edited(
    morphine, branch, counter, doctor
):
    """A page has to read a year later exactly as it read on the day it was written."""
    sell(morphine, branch, counter, doctor)

    doctor.name = "Dr Someone Else"
    doctor.registration_number = "NMC-99999"
    doctor.save(update_fields=["name", "registration_number", "updated_at"])

    entry = NarcoticRegisterEntry.objects.get()
    assert entry.prescriber_name == "Dr Anjana Thapa"
    assert entry.prescriber_registration_number == "NMC-12345"


def test_the_line_names_the_batch_that_actually_left(morphine, branch, counter, doctor):
    """Driven off the stock movement, so the register can be reconciled against the shelf."""
    sell(morphine, branch, counter, doctor)

    entry = NarcoticRegisterEntry.objects.get()
    assert entry.batch is not None
    assert entry.batch.number == "B1"
    assert entry.location is not None


def test_the_line_carries_the_invoice_number(morphine, branch, counter, doctor):
    issued = sell(morphine, branch, counter, doctor)
    assert NarcoticRegisterEntry.objects.get().document_number == issued.invoice.number


# --------------------------------------------------------------------------- the running balance
def test_the_balance_follows_the_entries(morphine, branch, counter, doctor):
    """Stock received outside a goods receipt is not in the register, so it starts at zero."""
    stock_up(morphine, branch, counter)
    assert total_balance_of(branch=branch, item=morphine.item) == Decimal("0")

    sell(morphine, branch, counter, doctor)
    assert total_balance_of(branch=branch, item=morphine.item) == Decimal("-10")


def test_each_line_records_the_balance_it_left_behind(morphine, branch, counter, doctor):
    for _ in range(3):
        sell(morphine, branch, counter, doctor)

    balances = [entry.balance_after for entry in NarcoticRegisterEntry.objects.all()]
    assert balances == [Decimal("-10"), Decimal("-20"), Decimal("-30")]


def test_a_register_that_adds_up_reports_no_discrepancy(morphine, branch, counter, doctor):
    sell(morphine, branch, counter, doctor)
    assert reconcile_register() == []


def test_a_balance_that_drifted_is_reported_not_repaired(morphine, branch, counter, doctor):
    """Something wrote outside this module. Correcting the number silently would hide that."""
    sell(morphine, branch, counter, doctor)
    NarcoticRegisterBalance.objects.update(quantity=Decimal("999"))

    found = reconcile_register()
    assert len(found) == 1
    assert found[0].balance_says == Decimal("999")
    assert found[0].entries_say == Decimal("-10")
    assert found[0].difference == Decimal("1009")

    # and the entries themselves are untouched
    assert NarcoticRegisterEntry.objects.get().quantity == Decimal("-10")


# --------------------------------------------------------------------------- immutability
def test_a_register_line_cannot_be_edited(morphine, branch, counter, doctor):
    from django.db import DatabaseError, transaction

    sell(morphine, branch, counter, doctor)
    entry = NarcoticRegisterEntry.objects.get()

    with pytest.raises(DatabaseError), transaction.atomic():
        NarcoticRegisterEntry.objects.filter(pk=entry.pk).update(quantity=Decimal("-1"))


def test_a_register_line_cannot_be_deleted(morphine, branch, counter, doctor):
    from django.db import DatabaseError, transaction

    sell(morphine, branch, counter, doctor)
    entry = NarcoticRegisterEntry.objects.get()

    with pytest.raises(DatabaseError), transaction.atomic():
        NarcoticRegisterEntry.objects.filter(pk=entry.pk).delete()


def test_a_correction_is_a_new_line_pointing_at_the_old_one(morphine, branch, counter, doctor):
    sell(morphine, branch, counter, doctor)
    original = NarcoticRegisterEntry.objects.get()

    correction = correct_entry(
        original, quantity=Decimal("2"), reason="Two tablets returned unopened"
    )

    assert correction.entry_type == RegisterEntryType.CORRECTION
    assert correction.corrects == original
    assert correction.balance_after == Decimal("-8")
    original.refresh_from_db()
    assert original.quantity == Decimal("-10")  # still says what it always said


def test_a_correction_without_a_reason_is_refused(morphine, branch, counter, doctor):
    """An unexplained correction is the shape a diversion takes."""
    sell(morphine, branch, counter, doctor)
    entry = NarcoticRegisterEntry.objects.get()

    with pytest.raises(DomainError) as caught:
        correct_entry(entry, quantity=Decimal("2"), reason="   ")
    assert caught.value.error.code == "REGISTER_CORRECTION_NEEDS_REASON"


def test_cancelling_a_bill_puts_the_stock_back_in_the_register(morphine, branch, counter, doctor):
    issued = sell(morphine, branch, counter, doctor)
    cancel_invoice(issued.invoice, reason="Customer changed their mind")

    lines = list(NarcoticRegisterEntry.objects.all())
    assert len(lines) == 2
    assert lines[1].entry_type == RegisterEntryType.CORRECTION
    assert lines[1].quantity == Decimal("10")
    assert lines[1].corrects == lines[0]
    assert balance_of(branch=branch, item=morphine.item) == Decimal("0")


# --------------------------------------------------------------------------- coming in
def receive(morphine, branch, location, supplier, *, strips="5"):
    receipt = start_receipt(
        branch=branch,
        location=location,
        supplier=supplier,
        supplier_invoice_number="SUP-1",
        supplier_invoice_date=TODAY,
        received_on=TODAY,
    )
    add_receipt_line(
        receipt,
        item=morphine.item,
        quantity=Decimal(strips),
        rate=Decimal("10"),
        batch_number="IN-1",
        expiry_date=TODAY + timedelta(days=365),
        mrp=Decimal("2.00"),
    )
    return post_receipt(receipt)


def test_receiving_a_narcotic_into_the_cabinet_writes_a_receipt_line(
    morphine, branch, cabinet, supplier
):
    receive(morphine, branch, cabinet, supplier)

    entry = NarcoticRegisterEntry.objects.get()
    assert entry.entry_type == RegisterEntryType.RECEIPT
    assert entry.quantity == Decimal("50")  # five strips of ten
    assert entry.supplier_name == supplier.name
    assert entry.supplier_invoice_number == "SUP-1"
    assert balance_of(branch=branch, item=morphine.item, batch=entry.batch) == Decimal("50")


def test_receiving_a_narcotic_onto_an_open_shelf_is_refused(morphine, branch, counter, supplier):
    """Controlled stock put away on the counter is a finding on its own."""
    with pytest.raises(DomainError) as caught:
        receive(morphine, branch, counter, supplier)
    assert caught.value.error.code == "CONTROLLED_DRUG_NEEDS_LOCKED_STORAGE"


def test_a_refused_delivery_leaves_no_stock_behind(morphine, branch, counter, supplier):
    """The hook runs inside the posting transaction, so the whole delivery rolls back."""
    from core.inventory.models import StockLedgerEntry

    with pytest.raises(DomainError):
        receive(morphine, branch, counter, supplier)

    assert not StockLedgerEntry.objects.filter(item=morphine.item).exists()
    assert not NarcoticRegisterEntry.objects.exists()


def test_an_ordinary_medicine_can_go_anywhere(paracetamol, branch, counter, supplier):
    receive(paracetamol, branch, counter, supplier)
    assert not NarcoticRegisterEntry.objects.exists()


def test_cancelling_a_delivery_takes_it_back_out_of_the_register(
    morphine, branch, cabinet, supplier
):
    posted = receive(morphine, branch, cabinet, supplier)
    cancel_receipt(posted.receipt, reason="Wrong consignment")

    lines = list(NarcoticRegisterEntry.objects.all())
    assert len(lines) == 2
    assert lines[1].entry_type == RegisterEntryType.CORRECTION
    assert lines[1].quantity == Decimal("-50")
    assert balance_of(branch=branch, item=morphine.item, batch=lines[0].batch) == Decimal("0")


# --------------------------------------------------------------------------- counting the cabinet
def test_a_count_that_agrees_writes_nothing(morphine, branch, cabinet, supplier):
    posted = receive(morphine, branch, cabinet, supplier)

    written = record_count(
        branch=branch,
        item=morphine.item,
        batch=posted.entries[0].batch,
        counted_quantity=Decimal("50"),
        occurred_on=TODAY,
        witness_name="Sita Sharma",
        reason="Monthly count",
    )
    assert written is None


def test_a_count_that_disagrees_records_the_difference(morphine, branch, cabinet, supplier):
    posted = receive(morphine, branch, cabinet, supplier)
    batch = posted.entries[0].batch

    written = record_count(
        branch=branch,
        item=morphine.item,
        batch=batch,
        counted_quantity=Decimal("48"),
        occurred_on=TODAY,
        witness_name="Sita Sharma",
        reason="Two tablets unaccounted for",
    )

    assert written is not None
    assert written.entry_type == RegisterEntryType.ADJUSTMENT
    assert written.quantity == Decimal("-2")
    assert written.witness_name == "Sita Sharma"
    assert balance_of(branch=branch, item=morphine.item, batch=batch) == Decimal("48")


def test_counting_a_batched_drug_without_naming_the_batch_is_refused(
    morphine, branch, cabinet, supplier
):
    """An adjustment naming no batch leaves every batch balance still wrong."""
    receive(morphine, branch, cabinet, supplier)

    with pytest.raises(DomainError) as caught:
        record_count(
            branch=branch,
            item=morphine.item,
            counted_quantity=Decimal("48"),
            occurred_on=TODAY,
            witness_name="Sita Sharma",
            reason="Monthly count",
        )
    assert caught.value.error.code == "REGISTER_COUNT_IS_PER_BATCH"


def test_a_count_with_no_witness_is_refused(morphine, branch, cabinet, supplier):
    """Counting controlled stock alone and writing down the number is not a control."""
    receive(morphine, branch, cabinet, supplier)

    with pytest.raises(DomainError) as caught:
        record_count(
            branch=branch,
            item=morphine.item,
            counted_quantity=Decimal("48"),
            occurred_on=TODAY,
            witness_name="",
            reason="Monthly count",
        )
    assert caught.value.error.code == "REGISTER_COUNT_NEEDS_WITNESS"


# --------------------------------------------------------------------------- who dispensed it
def test_a_pharmacist_is_recorded_with_their_registration(
    morphine, branch, counter, doctor, pharmacist
):
    sell(morphine, branch, counter, doctor, actor=pharmacist)

    entry = NarcoticRegisterEntry.objects.get()
    assert entry.dispensed_by == pharmacist
    assert entry.dispensed_by_registration_number == "NPC-4321"


def test_someone_without_a_pharmacy_registration_cannot_hand_it_over(
    morphine, branch, counter, doctor, counter_staff
):
    with pytest.raises(DomainError) as caught:
        sell(morphine, branch, counter, doctor, actor=counter_staff)
    assert caught.value.error.code == "PHARMACIST_REGISTRATION_REQUIRED"


def test_an_expired_registration_is_not_a_registration(
    morphine, branch, counter, doctor, pharmacist, expired_credential
):
    with pytest.raises(DomainError) as caught:
        sell(morphine, branch, counter, doctor, actor=pharmacist)
    assert caught.value.error.code == "PHARMACIST_REGISTRATION_REQUIRED"


def test_a_refused_dispensing_sells_nothing(morphine, branch, counter, doctor, counter_staff):
    """The hook runs inside the issuing transaction, so the bill does not stand either."""
    from core.sales.models import InvoiceStatus

    invoice = bill_for(morphine, branch, counter)
    prescribe(invoice, doctor)

    with pytest.raises(DomainError):
        issue_invoice(invoice, actor=counter_staff)

    invoice.refresh_from_db()
    assert invoice.status == InvoiceStatus.DRAFT
    assert not invoice.number


# --------------------------------------------------------------------------- reading it back
def test_the_page_reads_in_the_order_it_was_written(
    morphine, branch, cabinet, counter, doctor, supplier
):
    receive(morphine, branch, cabinet, supplier)
    sell(morphine, branch, counter, doctor)

    page = register_page(branch=branch, item=morphine.item, start=TODAY, end=TODAY)
    assert [line.entry_type for line in page] == [
        RegisterEntryType.RECEIPT,
        RegisterEntryType.DISPENSED,
    ]


def test_the_page_leaves_out_other_drugs(morphine, paracetamol, branch, cabinet, supplier):
    receive(morphine, branch, cabinet, supplier)
    assert register_page(branch=branch, item=paracetamol.item, start=TODAY, end=TODAY) == []


def test_which_group_is_registered_follows_the_rule_not_the_code(
    unclassified, branch, counter, doctor
):
    """Classify it as Ka and it starts being registered; the module hard-codes no drug list."""
    classify(unclassified, DrugSchedule.KA, reason="Confirmed narcotic")

    invoice = bill_for(unclassified, branch, counter)
    prescribe(invoice, doctor)
    issue_invoice(invoice)

    assert NarcoticRegisterEntry.objects.count() == 1
