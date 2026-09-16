"""Taking money at the counter, giving it back, and counting the drawer out."""

from decimal import Decimal

import pytest

from core.payments.models import (
    CashMovement,
    CashMovementKind,
    Payment,
    PaymentDirection,
    ShiftStatus,
)
from core.payments.services import (
    amount_outstanding,
    approve_shift,
    close_shift,
    install_default_modes,
    is_settled,
    open_shift,
    paid_amount,
    pay_out,
    record_cash_movement,
    record_payment,
    refund,
    refunded_amount,
    reverse_payment,
    settle_invoice,
    summarise,
)
from core.sales.returns import credit_invoice
from core.sales.services import add_line, issue_invoice, start_invoice
from shared.errors import DomainError

from .conftest import TODAY, stock_up

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("calendar", "document_types", "inside_tenant"),
]


def a_bill(paracetamol, branch, counter, *, strips="4"):
    """An issued bill for 80 rupees: four strips at 20."""
    stock_up(paracetamol, branch, counter)
    invoice = start_invoice(branch=branch, location=counter, invoice_date=TODAY)
    add_line(invoice, item=paracetamol, quantity=Decimal(strips))
    return issue_invoice(invoice).invoice


# --------------------------------------------------------------------------- the modes
def test_a_new_pharmacy_gets_something_to_press(inside_tenant):
    assert install_default_modes() == 8


def test_installing_twice_does_not_duplicate(modes):
    assert install_default_modes() == 0


def test_only_cash_gives_change(modes):
    assert modes["cash"].gives_change
    assert not modes["fonepay"].gives_change
    assert not modes["card"].gives_change


def test_a_wallet_has_to_carry_its_reference(modes):
    assert modes["esewa"].requires_reference
    assert not modes["cash"].requires_reference


# --------------------------------------------------------------------------- the shift
def test_a_till_opens_with_its_float(shift):
    assert shift.is_open
    assert shift.opening_float == Decimal("2000.00")


def test_two_people_cannot_share_one_drawer(branch, counter, cashier, shift):
    """A shortfall on a shared till belongs to both of them, which means neither is asked."""
    with pytest.raises(DomainError) as caught:
        open_shift(branch=branch, location=counter, cashier=cashier, business_date=TODAY)
    assert caught.value.error.code == "SHIFT_ALREADY_OPEN"


def test_cash_cannot_be_taken_with_no_till_open(branch, cash):
    with pytest.raises(DomainError) as caught:
        record_payment(branch=branch, mode=cash, amount=Decimal("100"), received_on=TODAY)
    assert caught.value.error.code == "NO_OPEN_SHIFT"


def test_a_wallet_payment_needs_no_drawer(branch, fonepay):
    """It settles to a bank account and reconciles against a statement, not against a count."""
    payment = record_payment(
        branch=branch,
        mode=fonepay,
        amount=Decimal("100"),
        reference="FP-12345",
        received_on=TODAY,
    )
    assert payment.shift is None


# --------------------------------------------------------------------------- taking money
def test_a_bill_paid_in_cash_is_settled(paracetamol, branch, counter, cash, shift):
    invoice = a_bill(paracetamol, branch, counter)
    settle_invoice(invoice, tenders=[(cash, invoice.payable_amount)], shift=shift)

    assert paid_amount(invoice) == invoice.payable_amount
    assert amount_outstanding(invoice) == Decimal("0.00")
    assert is_settled(invoice)


def test_change_is_worked_out_from_what_was_handed_over(paracetamol, branch, counter, cash, shift):
    invoice = a_bill(paracetamol, branch, counter)  # 80.00
    payments = settle_invoice(
        invoice,
        tenders=[(cash, invoice.payable_amount)],
        shift=shift,
        tendered_cash=Decimal("100"),
    )

    assert payments[0].tendered_amount == Decimal("100.00")
    assert payments[0].change_amount == Decimal("20.00")
    assert payments[0].amount == Decimal("80.00")


def test_change_cannot_come_out_of_a_card(branch, fonepay, shift):
    """One of the simplest ways to empty a till, so it is refused rather than warned about."""
    with pytest.raises(DomainError) as caught:
        record_payment(
            branch=branch,
            mode=fonepay,
            amount=Decimal("80"),
            tendered=Decimal("100"),
            reference="FP-1",
            shift=shift,
            received_on=TODAY,
        )
    assert caught.value.error.code == "CHANGE_ONLY_FROM_CASH"


def test_handing_over_too_little_is_refused(branch, cash, shift):
    with pytest.raises(DomainError) as caught:
        record_payment(
            branch=branch,
            mode=cash,
            amount=Decimal("80"),
            tendered=Decimal("50"),
            shift=shift,
            received_on=TODAY,
        )
    assert caught.value.error.code == "NOT_ENOUGH_TENDERED"


def test_a_wallet_payment_without_its_reference_is_refused(branch, fonepay, shift):
    with pytest.raises(DomainError) as caught:
        record_payment(
            branch=branch, mode=fonepay, amount=Decimal("80"), shift=shift, received_on=TODAY
        )
    assert caught.value.error.code == "REFERENCE_REQUIRED"


def test_a_bill_can_be_split_across_methods(paracetamol, branch, counter, cash, fonepay, shift):
    invoice = a_bill(paracetamol, branch, counter)  # 80.00
    settle_invoice(
        invoice,
        tenders=[(cash, Decimal("30")), (fonepay, Decimal("50"))],
        shift=shift,
        references={"fonepay": "FP-999"},
    )

    assert paid_amount(invoice) == Decimal("80.00")
    assert is_settled(invoice)


def test_a_part_payment_leaves_the_rest_owing(paracetamol, branch, counter, cash, shift):
    invoice = a_bill(paracetamol, branch, counter)  # 80.00
    settle_invoice(invoice, tenders=[(cash, Decimal("30"))], shift=shift)

    assert amount_outstanding(invoice) == Decimal("50.00")
    assert not is_settled(invoice)


def test_a_bill_cannot_be_overpaid(paracetamol, branch, counter, cash, shift):
    """A fat-fingered second tender would leave the accounts holding money nobody claimed."""
    invoice = a_bill(paracetamol, branch, counter)
    with pytest.raises(DomainError) as caught:
        settle_invoice(invoice, tenders=[(cash, Decimal("500"))], shift=shift)
    assert caught.value.error.code == "PAYMENT_EXCEEDS_WHAT_IS_DUE"


def test_crediting_a_bill_reduces_what_is_owed_on_it(paracetamol, branch, counter):
    """The customer never paid and the goods came back, so nothing is outstanding either."""
    invoice = a_bill(paracetamol, branch, counter)
    credit_invoice(invoice, reason="Returned unopened", confirmed=True)

    assert amount_outstanding(invoice) == Decimal("0.00")


# --------------------------------------------------------------------------- giving it back
def test_a_refund_goes_against_the_credit_note(paracetamol, branch, counter, cash, shift):
    invoice = a_bill(paracetamol, branch, counter)
    settle_invoice(invoice, tenders=[(cash, invoice.payable_amount)], shift=shift)
    note = credit_invoice(invoice, reason="Returned unopened", confirmed=True).credit_note

    given_back = refund(note, mode=cash, shift=shift)

    assert given_back.direction == PaymentDirection.OUT
    assert given_back.amount == invoice.payable_amount
    assert refunded_amount(note) == invoice.payable_amount


def test_a_credit_note_cannot_be_refunded_twice(paracetamol, branch, counter, cash, shift):
    invoice = a_bill(paracetamol, branch, counter)
    settle_invoice(invoice, tenders=[(cash, invoice.payable_amount)], shift=shift)
    note = credit_invoice(invoice, reason="Returned", confirmed=True).credit_note
    refund(note, mode=cash, shift=shift)

    with pytest.raises(DomainError) as caught:
        refund(note, mode=cash, shift=shift)
    assert caught.value.error.code == "PAYMENT_EXCEEDS_WHAT_IS_DUE"


# --------------------------------------------------------------------------- it is evidence
def test_a_payment_cannot_be_edited(branch, cash, shift):
    from django.db import DatabaseError, transaction

    payment = record_payment(
        branch=branch, mode=cash, amount=Decimal("100"), shift=shift, received_on=TODAY
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        Payment.objects.filter(pk=payment.pk).update(amount=Decimal("1"))


def test_a_payment_cannot_be_deleted(branch, cash, shift):
    from django.db import DatabaseError, transaction

    payment = record_payment(
        branch=branch, mode=cash, amount=Decimal("100"), shift=shift, received_on=TODAY
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        Payment.objects.filter(pk=payment.pk).delete()


def test_a_mistake_is_corrected_by_its_opposite(branch, cash, shift):
    payment = record_payment(
        branch=branch, mode=cash, amount=Decimal("100"), shift=shift, received_on=TODAY
    )
    reversal = reverse_payment(payment, reason="Rang up the wrong customer")

    assert reversal.direction == PaymentDirection.OUT
    assert reversal.reverses == payment
    assert summarise(shift).cash_taken == Decimal("0.00")


def test_a_reversal_without_a_reason_is_refused(branch, cash, shift):
    payment = record_payment(
        branch=branch, mode=cash, amount=Decimal("100"), shift=shift, received_on=TODAY
    )
    with pytest.raises(DomainError) as caught:
        reverse_payment(payment, reason="  ")
    assert caught.value.error.code == "CASH_MOVEMENT_NEEDS_A_REASON"


def test_reversing_twice_is_refused(branch, cash, shift):
    payment = record_payment(
        branch=branch, mode=cash, amount=Decimal("100"), shift=shift, received_on=TODAY
    )
    reverse_payment(payment, reason="Wrong customer")

    with pytest.raises(DomainError) as caught:
        reverse_payment(payment, reason="Wrong again")
    assert caught.value.error.code == "PAYMENT_ALREADY_REVERSED"


# --------------------------------------------------------------------------- the drawer
def test_money_out_of_the_till_needs_a_witness(shift):
    """One person deciding alone that six hundred rupees left for a taxi is not a control."""
    with pytest.raises(DomainError) as caught:
        pay_out(shift, amount=Decimal("600"), reason="Taxi to the wholesaler", witness_name="")
    assert caught.value.error.code == "CASH_OUT_NEEDS_A_WITNESS"


def test_money_out_of_the_till_needs_a_reason(shift):
    with pytest.raises(DomainError) as caught:
        pay_out(shift, amount=Decimal("600"), reason="   ", witness_name="Hari")
    assert caught.value.error.code == "CASH_MOVEMENT_NEEDS_A_REASON"


def test_a_petty_expense_comes_out_of_the_expected_cash(shift):
    pay_out(shift, amount=Decimal("600"), reason="Taxi to the wholesaler", witness_name="Hari")
    assert summarise(shift).expected_cash == Decimal("1400.00")


def test_topping_up_the_float_needs_no_witness(shift):
    """Money going in is not the direction anybody steals in."""
    record_cash_movement(
        shift, kind=CashMovementKind.FLOAT_IN, amount=Decimal("1000"), reason="Ran out of change"
    )
    assert summarise(shift).expected_cash == Decimal("3000.00")


def test_a_cash_movement_cannot_be_edited(shift):
    from django.db import DatabaseError, transaction

    movement = pay_out(shift, amount=Decimal("100"), reason="Tea", witness_name="Hari")
    with pytest.raises(DatabaseError), transaction.atomic():
        CashMovement.objects.filter(pk=movement.pk).update(amount=Decimal("-1"))


# --------------------------------------------------------------------------- counting out
def test_the_summary_is_what_the_z_report_prints(
    paracetamol, branch, counter, cash, fonepay, shift
):
    invoice = a_bill(paracetamol, branch, counter)
    settle_invoice(
        invoice,
        tenders=[(cash, Decimal("30")), (fonepay, Decimal("50"))],
        shift=shift,
        references={"fonepay": "FP-1"},
    )

    summary = summarise(shift)
    assert summary.by_mode == {"cash": Decimal("30.00"), "fonepay": Decimal("50.00")}
    assert summary.cash_received == Decimal("30.00")
    assert summary.expected_cash == Decimal("2030.00")
    assert summary.payment_count == 2


def test_change_given_is_not_subtracted_twice(paracetamol, branch, counter, cash, shift):
    """A hundred handed over for an eighty-rupee bill leaves eighty in the drawer, not sixty."""
    invoice = a_bill(paracetamol, branch, counter)
    settle_invoice(
        invoice,
        tenders=[(cash, invoice.payable_amount)],
        shift=shift,
        tendered_cash=Decimal("100"),
    )
    assert summarise(shift).expected_cash == Decimal("2080.00")


def test_a_drawer_that_matches_closes_without_an_explanation(
    paracetamol, branch, counter, cash, shift
):
    invoice = a_bill(paracetamol, branch, counter)  # 80.00
    settle_invoice(invoice, tenders=[(cash, invoice.payable_amount)], shift=shift)

    closed = close_shift(shift, counts={1000: 2, 50: 1, 20: 1, 10: 1})
    assert closed.status == ShiftStatus.CLOSED
    assert closed.counted_cash == Decimal("2080.00")
    assert closed.variance == Decimal("0.00")


def test_a_short_drawer_is_recorded_not_corrected(shift):
    """A till short by four hundred is a fact about the day. Writing it off destroys the signal."""
    closed = close_shift(
        shift, counts={1000: 1, 500: 1, 100: 1}, variance_reason="Cannot account for it"
    )

    assert closed.counted_cash == Decimal("1600.00")
    assert closed.expected_cash == Decimal("2000.00")
    assert closed.variance == Decimal("-400.00")
    assert closed.is_short


def test_a_difference_will_not_close_without_an_explanation(shift):
    with pytest.raises(DomainError) as caught:
        close_shift(shift, counts={1000: 1, 500: 1, 100: 1})
    assert caught.value.error.code == "VARIANCE_NEEDS_AN_EXPLANATION"
    assert "short by 400.00" in caught.value.message


def test_a_rupee_out_closes_quietly(branch, cash, shift):
    record_payment(branch=branch, mode=cash, amount=Decimal("1"), shift=shift, received_on=TODAY)
    closed = close_shift(shift, counts={1000: 2})
    assert closed.variance == Decimal("-1.00")
    assert closed.status == ShiftStatus.CLOSED


def test_the_denomination_sheet_is_kept_not_just_the_total(shift):
    close_shift(shift, counts={1000: 2})
    counted = {row.value: row.count for row in shift.denominations.all()}
    assert counted == {1000: 2}


def test_something_that_is_not_a_nepali_note_is_refused(shift):
    with pytest.raises(DomainError) as caught:
        close_shift(shift, counts={1000: 2, 200: 1})
    assert caught.value.error.code == "UNKNOWN_DENOMINATION"


def test_a_closed_till_cannot_be_closed_again(shift):
    close_shift(shift, counts={1000: 2})
    with pytest.raises(DomainError) as caught:
        close_shift(shift, counts={1000: 2})
    assert caught.value.error.code == "SHIFT_ALREADY_CLOSED"


def test_a_closed_till_takes_no_more_cash_movements(shift):
    close_shift(shift, counts={1000: 2})
    with pytest.raises(DomainError) as caught:
        pay_out(shift, amount=Decimal("100"), reason="Tea", witness_name="Hari")
    assert caught.value.error.code == "SHIFT_ALREADY_CLOSED"


# --------------------------------------------------------------------------- signing off
def test_a_supervisor_signs_the_count_off(shift, supervisor):
    close_shift(shift, counts={1000: 2})
    approved = approve_shift(shift, approver=supervisor, note="Counted with the cashier")

    assert approved.approved_by == supervisor
    assert approved.approved_at is not None


def test_an_open_till_cannot_be_signed_off(shift, supervisor):
    with pytest.raises(DomainError) as caught:
        approve_shift(shift, approver=supervisor)
    assert caught.value.error.code == "SHIFT_ALREADY_CLOSED"


def test_closing_and_signing_off_are_both_in_the_trail(shift, supervisor, cashier):
    from kernel.audit.models import AuditEvent

    close_shift(shift, counts={1000: 1, 500: 1, 100: 1}, actor=cashier, variance_reason="Short")
    approve_shift(shift, approver=supervisor)

    events = list(AuditEvent.objects.filter(entity_id=str(shift.pk)).order_by("sequence"))
    assert events[-2].changes["variance"]["to"] == "-400.00"
    assert events[-2].reason == "Short"
    assert events[-1].changes["approved_by"]["to"] == "Hari Thapa"
