"""Selling on account: the limit, the overdue block, and what the customer owes."""

from datetime import timedelta
from decimal import Decimal

import pytest

from core.parties.models import Party
from core.payments.credit import (
    ageing,
    assess,
    open_invoices,
    opening_balance,
    outstanding_for,
    overdue_for,
    statement,
)
from core.payments.services import receive_against, settle_invoice
from core.sales.returns import credit_invoice
from core.sales.services import add_line, issue_invoice, start_invoice
from shared.errors import DomainError

from .conftest import TODAY, stock_up

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("calendar", "document_types", "inside_tenant"),
]


@pytest.fixture
def clinic():
    """A regular account customer: a clinic that settles monthly."""
    return Party.objects.create(
        name="Shanti Clinic",
        is_customer=True,
        credit_limit=Decimal("5000"),
        credit_days=30,
        phone="9800000001",
    )


@pytest.fixture
def walk_in():
    return Party.objects.create(name="Ram Bahadur", is_customer=True)


def a_bill(paracetamol, branch, counter, customer=None, *, strips="4", on_date=None):
    """An issued bill for 80 rupees, optionally against a customer's account."""
    stock_up(paracetamol, branch, counter)
    invoice = start_invoice(
        branch=branch,
        location=counter,
        invoice_date=on_date or TODAY,
        customer=customer,
    )
    add_line(invoice, item=paracetamol, quantity=Decimal(strips))
    return issue_invoice(invoice).invoice


def on_tick(invoice, on_account, **kwargs):
    """Put the whole bill on the customer's account."""
    return settle_invoice(invoice, tenders=[(on_account, invoice.payable_amount)], **kwargs)


def lower_the_limit(clinic, amount="50"):
    clinic.credit_limit = Decimal(amount)
    clinic.save(update_fields=["credit_limit", "updated_at"])
    return clinic


# --------------------------------------------------------------------------- the decision
def test_a_customer_within_their_limit_may_buy_on_account(clinic):
    decision = assess(clinic, amount=Decimal("1000"), on_date=TODAY)
    assert decision.allowed
    assert decision.headroom == Decimal("5000.00")


def test_a_customer_with_no_limit_set_gets_no_credit(walk_in):
    """Zero means no credit, not unlimited. Defaulting the other way would be a disaster."""
    decision = assess(walk_in, amount=Decimal("100"), on_date=TODAY)
    assert not decision.allowed
    assert "no credit limit" in decision.reason


def test_the_decision_says_by_how_much_it_would_go_over(
    clinic, on_account, paracetamol, branch, counter
):
    """So the counter can have the conversation, rather than reading out a bare refusal."""
    for _ in range(60):  # sixty bills of eighty = 4,800
        on_tick(a_bill(paracetamol, branch, counter, clinic), on_account)

    decision = assess(clinic, amount=Decimal("500"), on_date=TODAY)
    assert not decision.allowed
    assert decision.exposure == Decimal("4800.00")
    assert decision.would_exceed_by == Decimal("300.00")


# --------------------------------------------------------------------------- at the counter
def test_a_sale_on_account_needs_a_named_customer(paracetamol, branch, counter, on_account):
    """A walk-in is somebody nobody can send a statement to."""
    invoice = a_bill(paracetamol, branch, counter)
    with pytest.raises(DomainError) as caught:
        on_tick(invoice, on_account)
    assert caught.value.error.code == "CREDIT_NEEDS_A_NAMED_CUSTOMER"


def test_an_account_sale_within_the_limit_goes_through(
    paracetamol, branch, counter, clinic, on_account
):
    on_tick(a_bill(paracetamol, branch, counter, clinic), on_account)
    assert outstanding_for(clinic) == Decimal("80.00")


def test_going_past_the_limit_is_refused(paracetamol, branch, counter, clinic, on_account):
    lower_the_limit(clinic)
    with pytest.raises(DomainError) as caught:
        on_tick(a_bill(paracetamol, branch, counter, clinic), on_account)
    assert caught.value.error.code == "CREDIT_LIMIT_EXCEEDED"


def test_an_overdue_bill_blocks_the_next_one(paracetamol, branch, counter, clinic, on_account):
    """A customer inside their limit who never pays is the worse risk of the two."""
    old = a_bill(paracetamol, branch, counter, clinic, on_date=TODAY - timedelta(days=90))
    on_tick(old, on_account)

    with pytest.raises(DomainError) as caught:
        on_tick(a_bill(paracetamol, branch, counter, clinic), on_account)
    assert caught.value.error.code == "CUSTOMER_HAS_OVERDUE_BILLS"


# --------------------------------------------------------------------------- on account is not paid
def test_putting_a_bill_on_account_is_not_the_money_arriving(
    paracetamol, branch, counter, clinic, on_account
):
    """Counting it as received is how a ledger shows nothing owed while the shop is owed a lot."""
    invoice = a_bill(paracetamol, branch, counter, clinic)
    on_tick(invoice, on_account)

    assert outstanding_for(clinic) == Decimal("80.00")
    assert [open_invoice.pk for open_invoice in open_invoices(clinic)] == [invoice.pk]


def test_paying_it_off_clears_the_exposure(
    paracetamol, branch, counter, clinic, on_account, cash, shift
):
    invoice = a_bill(paracetamol, branch, counter, clinic)
    on_tick(invoice, on_account)
    invoice.refresh_from_db()

    receive_against(invoice, mode=cash, amount=Decimal("80"), shift=shift, received_on=TODAY)

    assert outstanding_for(clinic) == Decimal("0.00")
    assert open_invoices(clinic) == []


def test_a_settled_account_cannot_be_paid_twice(
    paracetamol, branch, counter, clinic, on_account, cash, shift
):
    invoice = a_bill(paracetamol, branch, counter, clinic)
    on_tick(invoice, on_account)
    invoice.refresh_from_db()
    receive_against(invoice, mode=cash, amount=Decimal("80"), shift=shift, received_on=TODAY)

    with pytest.raises(DomainError) as caught:
        receive_against(invoice, mode=cash, amount=Decimal("80"), shift=shift, received_on=TODAY)
    assert caught.value.error.code == "PAYMENT_EXCEEDS_WHAT_IS_DUE"


def test_a_bill_cannot_be_put_on_account_twice_over(
    paracetamol, branch, counter, clinic, on_account
):
    """Neither tender brings money in, so without a guard neither would be noticed."""
    invoice = a_bill(paracetamol, branch, counter, clinic)
    on_tick(invoice, on_account)

    with pytest.raises(DomainError) as caught:
        on_tick(invoice, on_account)
    assert caught.value.error.code == "PAYMENT_EXCEEDS_WHAT_IS_DUE"


# --------------------------------------------------------------------------- overriding it
def test_an_override_lets_it_through_and_is_recorded(
    paracetamol, branch, counter, clinic, on_account, supervisor
):
    from kernel.audit.models import AuditAction, AuditEvent

    lower_the_limit(clinic)
    on_tick(
        a_bill(paracetamol, branch, counter, clinic),
        on_account,
        override_reason="Owner approved by phone",
        override_by=supervisor,
    )

    event = AuditEvent.objects.filter(action=AuditAction.OVERRIDE).order_by("-sequence").first()
    assert event.reason == "Owner approved by phone"
    assert event.actor == supervisor
    assert event.entity_label == "Shanti Clinic"


def test_an_override_with_no_reason_is_not_an_override(
    paracetamol, branch, counter, clinic, on_account, supervisor
):
    lower_the_limit(clinic)
    with pytest.raises(DomainError) as caught:
        on_tick(
            a_bill(paracetamol, branch, counter, clinic),
            on_account,
            override_reason="   ",
            override_by=supervisor,
        )
    assert caught.value.error.code == "CREDIT_LIMIT_EXCEEDED"


def test_an_override_with_no_name_is_refused(paracetamol, branch, counter, clinic, on_account):
    """An override nobody signed is the same as no control at all."""
    lower_the_limit(clinic)
    with pytest.raises(DomainError) as caught:
        on_tick(
            a_bill(paracetamol, branch, counter, clinic),
            on_account,
            override_reason="Owner said yes",
        )
    assert caught.value.error.code == "OVERRIDE_NEEDS_A_NAME"


# --------------------------------------------------------------------------- the due date
def test_the_due_date_is_frozen_when_the_sale_goes_on_account(
    paracetamol, branch, counter, clinic, on_account
):
    invoice = a_bill(paracetamol, branch, counter, clinic)
    on_tick(invoice, on_account)

    invoice.refresh_from_db()
    assert invoice.due_date == TODAY + timedelta(days=30)


def test_shortening_the_terms_does_not_make_old_bills_late(
    paracetamol, branch, counter, clinic, on_account
):
    """Otherwise tightening the terms turns settled history into a list of late payments."""
    invoice = a_bill(paracetamol, branch, counter, clinic)
    on_tick(invoice, on_account)

    clinic.credit_days = 0
    clinic.save(update_fields=["credit_days", "updated_at"])

    invoice.refresh_from_db()
    assert invoice.due_date == TODAY + timedelta(days=30)
    assert overdue_for(clinic, as_of=TODAY + timedelta(days=10)) == Decimal("0.00")


# --------------------------------------------------------------------------- what they owe
def test_a_credit_note_reduces_what_they_owe(paracetamol, branch, counter, clinic, on_account):
    invoice = a_bill(paracetamol, branch, counter, clinic)
    on_tick(invoice, on_account)
    invoice.refresh_from_db()
    credit_invoice(invoice, reason="Returned unopened", confirmed=True)

    assert outstanding_for(clinic) == Decimal("0.00")


def test_ageing_splits_it_by_how_long_it_has_been_owed(
    paracetamol, branch, counter, clinic, on_account
):
    """Not "they owe 80" but "80 of it has been sitting since Ashadh"."""
    old = a_bill(paracetamol, branch, counter, clinic, on_date=TODAY - timedelta(days=100))
    on_tick(old, on_account)

    buckets = ageing(clinic, as_of=TODAY)
    assert buckets["61-90"] == Decimal("80.00")
    assert sum(buckets.values()) == Decimal("80.00")


def test_a_bill_not_yet_due_sits_in_current(paracetamol, branch, counter, clinic, on_account):
    on_tick(a_bill(paracetamol, branch, counter, clinic), on_account)
    assert ageing(clinic, as_of=TODAY)["current"] == Decimal("80.00")


# --------------------------------------------------------------------------- the statement
def test_the_statement_runs_a_balance(
    paracetamol, branch, counter, clinic, on_account, cash, shift
):
    """Two bills of eighty, one of them paid in cash: eighty still owed."""
    on_tick(a_bill(paracetamol, branch, counter, clinic), on_account)
    second = a_bill(paracetamol, branch, counter, clinic)
    settle_invoice(second, tenders=[(cash, second.payable_amount)], shift=shift)

    lines = statement(clinic, start=TODAY, end=TODAY)
    assert [line.kind for line in lines] == ["invoice", "invoice", "payment"]
    assert lines[-1].balance == Decimal("80.00")


def test_a_credit_note_shows_on_the_statement_as_a_credit(
    paracetamol, branch, counter, clinic, on_account
):
    invoice = a_bill(paracetamol, branch, counter, clinic)
    on_tick(invoice, on_account)
    invoice.refresh_from_db()
    credit_invoice(invoice, reason="Returned unopened", confirmed=True)

    lines = statement(clinic, start=TODAY, end=TODAY)
    note_line = next(line for line in lines if line.kind == "credit_note")
    assert note_line.credit == Decimal("80.00")
    assert lines[-1].balance == Decimal("0.00")


def test_the_statement_opens_from_what_was_owed_before_it(
    paracetamol, branch, counter, clinic, on_account
):
    old = a_bill(paracetamol, branch, counter, clinic, on_date=TODAY - timedelta(days=5))
    on_tick(old, on_account)

    assert statement(clinic, start=TODAY, end=TODAY) == []
    assert opening_balance(clinic, before=TODAY) == Decimal("80.00")
