"""The drug schedule decides what has to happen before a medicine is handed over."""

from datetime import timedelta
from decimal import Decimal

import pytest

from core.sales.services import issue_invoice
from modules.pharmacy.dispensing import requirements_for
from modules.pharmacy.models import DrugSchedule, Prescription, ScheduleRule
from modules.pharmacy.services import classify, rule_for
from shared.errors import DomainError

from .conftest import TODAY, bill_for

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("calendar", "document_types", "inside_tenant"),
]


def prescribe(invoice, doctor, *, prescribed_on=None, valid_until=None):
    return Prescription.objects.create(
        invoice=invoice,
        prescriber=doctor,
        patient_name="Ram Bahadur",
        prescribed_on=prescribed_on or TODAY,
        valid_until=valid_until,
    )


# --------------------------------------------------------------------------- the rules
def test_the_rules_are_seeded_for_every_group():
    for schedule in DrugSchedule.values:
        assert rule_for(schedule, on_date=TODAY) is not None


def test_both_ka_and_kha_require_a_prescription():
    """The research correction: the BRD had treated only Kha as the prescription tier."""
    assert rule_for(DrugSchedule.KA, on_date=TODAY).requires_prescription
    assert rule_for(DrugSchedule.KHA, on_date=TODAY).requires_prescription


def test_ga_needs_no_prescription_but_needs_a_pharmacist():
    rule = rule_for(DrugSchedule.GA, on_date=TODAY)
    assert not rule.requires_prescription
    assert rule.requires_pharmacist


def test_only_ka_needs_a_statutory_register_entry():
    assert rule_for(DrugSchedule.KA, on_date=TODAY).requires_register_entry
    assert not rule_for(DrugSchedule.KHA, on_date=TODAY).requires_register_entry


def test_the_seeded_rules_say_they_are_unverified():
    """Nothing here may be relied on until CR-DDA-01 is closed against the Act."""
    for schedule in (DrugSchedule.KA, DrugSchedule.KHA, DrugSchedule.GA):
        assert "CR-DDA-01" in rule_for(schedule, on_date=TODAY).source_note


def test_a_rule_change_does_not_rewrite_the_past():
    """A DDA notice is a new dated rule, so last year's sales stay judged by last year's rule."""
    original = rule_for(DrugSchedule.GA, on_date=TODAY)
    original.effective_to = TODAY
    original.save(update_fields=["effective_to"])
    ScheduleRule.objects.create(
        schedule=DrugSchedule.GA,
        requires_prescription=True,
        effective_from=TODAY + timedelta(days=1),
        source_note="Tightened by notice",
    )

    assert not rule_for(DrugSchedule.GA, on_date=TODAY).requires_prescription
    assert rule_for(DrugSchedule.GA, on_date=TODAY + timedelta(days=1)).requires_prescription


# --------------------------------------------------------------------------- at the counter
def test_an_over_the_counter_medicine_sells_without_a_prescription(paracetamol, branch, counter):
    invoice = bill_for(paracetamol, branch, counter)
    issued = issue_invoice(invoice)
    assert issued.invoice.number


def test_an_antibiotic_without_a_prescription_is_refused(amoxicillin, branch, counter):
    """Samuha Kha. Selling antibiotics over the counter is exactly what the rule exists to stop."""
    invoice = bill_for(amoxicillin, branch, counter)
    with pytest.raises(DomainError) as caught:
        issue_invoice(invoice)

    assert caught.value.error.code == "PRESCRIPTION_REQUIRED"
    assert caught.value.error.message_ne


def test_an_antibiotic_with_a_prescription_sells(amoxicillin, branch, counter, doctor):
    invoice = bill_for(amoxicillin, branch, counter)
    prescribe(invoice, doctor)
    assert issue_invoice(invoice).invoice.number


def test_a_narcotic_without_a_prescription_is_refused(morphine, branch, counter):
    invoice = bill_for(morphine, branch, counter)
    with pytest.raises(DomainError) as caught:
        issue_invoice(invoice)
    assert caught.value.error.code == "PRESCRIPTION_REQUIRED"


def test_an_unclassified_medicine_is_refused_until_it_is_classified(
    unclassified, branch, counter, doctor
):
    """Treated as restricted: guessing the other way means handing over a controlled drug."""
    invoice = bill_for(unclassified, branch, counter)
    prescribe(invoice, doctor)

    with pytest.raises(DomainError) as caught:
        issue_invoice(invoice)
    assert caught.value.error.code == "MEDICINE_NOT_CLASSIFIED"


def test_classifying_it_lets_it_be_sold(unclassified, branch, counter):
    invoice = bill_for(unclassified, branch, counter)
    classify(unclassified, DrugSchedule.GA, reason="Confirmed against the DDA list")
    assert issue_invoice(invoice).invoice.number


def test_classifying_a_medicine_is_recorded(unclassified):
    from kernel.audit.models import AuditEvent

    classify(unclassified, DrugSchedule.KA, reason="Narcotic")
    event = AuditEvent.objects.order_by("-sequence").first()
    assert event.changes["schedule"]["to"] == DrugSchedule.KA
    assert event.reason == "Narcotic"
    unclassified.refresh_from_db()
    assert unclassified.is_narcotic


# --------------------------------------------------------------------------- prescriptions
def test_an_out_of_date_prescription_is_refused(amoxicillin, branch, counter, doctor):
    invoice = bill_for(amoxicillin, branch, counter)
    prescribe(
        invoice,
        doctor,
        prescribed_on=TODAY - timedelta(days=200),
        valid_until=TODAY - timedelta(days=100),
    )
    with pytest.raises(DomainError) as caught:
        issue_invoice(invoice)
    assert caught.value.error.code == "PRESCRIPTION_EXPIRED"


def test_a_prescription_with_no_end_date_stays_valid(amoxicillin, branch, counter, doctor):
    invoice = bill_for(amoxicillin, branch, counter)
    prescribe(invoice, doctor, prescribed_on=TODAY - timedelta(days=30))
    assert issue_invoice(invoice).invoice.number


def test_a_prescription_dated_in_the_future_is_not_valid_yet(amoxicillin, branch, counter, doctor):
    invoice = bill_for(amoxicillin, branch, counter)
    prescribe(invoice, doctor, prescribed_on=TODAY + timedelta(days=1))
    with pytest.raises(DomainError) as caught:
        issue_invoice(invoice)
    assert caught.value.error.code == "PRESCRIPTION_EXPIRED"


def test_a_prescriber_with_no_registration_number_is_refused_for_scheduled_drugs(
    amoxicillin, branch, counter, unregistered_doctor
):
    invoice = bill_for(amoxicillin, branch, counter)
    prescribe(invoice, unregistered_doctor)
    with pytest.raises(DomainError) as caught:
        issue_invoice(invoice)
    assert caught.value.error.code == "PRESCRIBER_REGISTRATION_REQUIRED"


def test_a_prescriber_can_be_recorded_before_being_verified(unregistered_doctor):
    """Refusing the record because the number was unreadable would just lose the sale entirely."""
    assert not unregistered_doctor.is_verified
    unregistered_doctor.verify(on_date=TODAY, note="Checked against the NMC register")
    assert unregistered_doctor.is_verified


# --------------------------------------------------------------------------- guidance
def test_the_counter_can_see_what_a_bill_needs(amoxicillin, morphine, branch, counter):
    from core.sales.services import add_line

    from .conftest import stock_up

    invoice = bill_for(amoxicillin, branch, counter)
    stock_up(morphine, branch, counter)
    add_line(invoice, item=morphine.item, quantity=Decimal("1"))

    needs = requirements_for(invoice)
    assert set(needs["prescription_required_for"]) == {
        "Amoxicillin 500mg",
        "Morphine 10mg",
    }
    assert needs["register_entry_required_for"] == ["Morphine 10mg"]
    assert needs["has_prescription"] is False


def test_a_refused_sale_consumes_no_invoice_number(amoxicillin, branch, counter):
    """The check runs before a number is taken, so a refusal leaves no gap in the run."""
    from kernel.numbering.services import preview_next

    invoice = bill_for(amoxicillin, branch, counter)
    before = preview_next(document_type="sales.invoice", branch=branch, on_date=TODAY)

    with pytest.raises(DomainError):
        issue_invoice(invoice)

    assert preview_next(document_type="sales.invoice", branch=branch, on_date=TODAY) == before


def test_a_bill_with_no_medicines_on_it_is_unaffected(branch, counter):
    """The check is registered globally, so it must do nothing when there is nothing to check."""
    from core.catalog.models import UnitOfMeasure
    from core.catalog.services import create_item
    from core.inventory.services import receive_stock
    from core.sales.services import add_line, start_invoice
    from core.tax.models import TaxCategory

    soap = create_item(
        code="SOAP-01",
        name="Soap",
        base_unit=UnitOfMeasure.objects.get(code="pcs"),
        tax_category=TaxCategory.objects.get(code="vat-standard"),
        is_batch_tracked=False,
        is_expiry_tracked=False,
        mrp=Decimal("50"),
    )
    receive_stock(
        item=soap, branch=branch, location=counter, quantity=Decimal("10"), occurred_on=TODAY
    )
    invoice = start_invoice(branch=branch, location=counter, invoice_date=TODAY)
    add_line(invoice, item=soap, quantity=Decimal("1"))
    assert issue_invoice(invoice).invoice.number
