"""What leaves a trail and what does not, across the whole stack.

Lives here rather than with the audit kernel because deciding *which* tables are logged is a
question about the business, not about the trail, and only a module sits above all of them.
"""

import pytest

from core.catalog.models import Item
from core.inventory.models import Batch, StockBalance, StockLedgerEntry
from core.parties.models import Party
from core.practitioners.models import Practitioner
from core.purchasing.models import GoodsReceipt
from core.sales.models import CreditNote, CreditNoteLine, SalesInvoice, SalesInvoiceLine
from core.tax.models import TaxCategory, TaxRate
from kernel.audit import tracking
from kernel.audit.models import AuditEvent
from modules.pharmacy.models import (
    MedicineProfile,
    NarcoticRegisterBalance,
    NarcoticRegisterEntry,
    Prescription,
    ScheduleRule,
)


def test_everything_a_pharmacy_is_inspected_on_leaves_a_trail():
    """Prices, tax rates, drug schedules, batches, bills, credit notes, prescribers, patients."""
    for model in (
        Item,
        Batch,
        Party,
        Practitioner,
        TaxCategory,
        TaxRate,
        GoodsReceipt,
        SalesInvoice,
        SalesInvoiceLine,
        CreditNote,
        CreditNoteLine,
        MedicineProfile,
        Prescription,
        ScheduleRule,
    ):
        assert tracking.is_tracked(model), f"{model._meta.label} has no trail"


def test_the_logs_are_not_logged_a_second_time():
    """The stock ledger and the narcotic register already are logs.

    Both are append-only in the database and both carry the actor, the document and the reason.
    Tracking them would write every scan at the counter twice — and take the tenant's hash-chain
    lock on the hot path to do it. Balances are a running total derived from the ledger, not a
    record of anything, and the trail itself would be a loop.
    """
    for model in (
        StockLedgerEntry,
        StockBalance,
        NarcoticRegisterEntry,
        NarcoticRegisterBalance,
        AuditEvent,
    ):
        assert not tracking.is_tracked(model), f"{model._meta.label} is its own log"


@pytest.mark.django_db
@pytest.mark.usefixtures("calendar", "document_types", "inside_tenant")
def test_reclassifying_a_drug_leaves_one_clear_entry_not_two(unclassified):
    """The service says it better than a row diff, so the row-level entry stands aside."""
    from modules.pharmacy.models import DrugSchedule
    from modules.pharmacy.services import classify

    before = AuditEvent.objects.count()
    classify(unclassified, DrugSchedule.KA, reason="Confirmed narcotic")

    assert AuditEvent.objects.count() == before + 1
    event = AuditEvent.objects.order_by("-sequence").first()
    assert event.changes["schedule"]["to"] == DrugSchedule.KA
    assert event.reason == "Confirmed narcotic"


@pytest.mark.django_db
@pytest.mark.usefixtures("calendar", "document_types", "inside_tenant")
def test_a_prescription_is_recorded_without_anybody_writing_a_log_call(
    amoxicillin, branch, counter, doctor
):
    from .conftest import bill_for

    invoice = bill_for(amoxicillin, branch, counter)
    prescription = Prescription.objects.create(
        invoice=invoice,
        prescriber=doctor,
        patient_name="Ram Bahadur",
        prescribed_on=invoice.invoice_date,
    )

    event = AuditEvent.objects.filter(entity_id=str(prescription.pk)).first()
    assert event is not None
    assert event.changes["patient_name"]["to"] == "Ram Bahadur"
