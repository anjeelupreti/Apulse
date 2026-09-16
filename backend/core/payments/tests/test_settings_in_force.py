"""A setting is worth nothing unless changing it changes what happens at the counter."""

from datetime import timedelta
from decimal import Decimal

import pytest

from core.parties.models import Party
from core.payments.credit import assess
from core.payments.services import close_shift, open_shift, pay_out, settle_invoice
from core.sales.services import add_line, issue_invoice, start_invoice
from kernel.settings import services as settings
from kernel.settings.registry import Scope
from shared.errors import DomainError

from .conftest import TODAY, stock_up

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("calendar", "document_types", "inside_tenant"),
]


@pytest.fixture
def clinic():
    return Party.objects.create(
        name="Shanti Clinic", is_customer=True, credit_limit=Decimal("50"), credit_days=30
    )


def a_bill(paracetamol, branch, counter, customer=None, *, on_date=None):
    """An issued bill for 80 rupees — more than the clinic's 50-rupee limit."""
    stock_up(paracetamol, branch, counter)
    invoice = start_invoice(
        branch=branch, location=counter, invoice_date=on_date or TODAY, customer=customer
    )
    add_line(invoice, item=paracetamol, quantity=Decimal("4"))
    return issue_invoice(invoice).invoice


# --------------------------------------------------------------------------- block or warn
def test_by_default_going_over_the_limit_blocks(paracetamol, branch, counter, clinic, on_account):
    invoice = a_bill(paracetamol, branch, counter, clinic)
    with pytest.raises(DomainError) as caught:
        settle_invoice(invoice, tenders=[(on_account, invoice.payable_amount)])
    assert caught.value.error.code == "CREDIT_LIMIT_EXCEEDED"


def test_a_pharmacy_can_choose_to_warn_instead(paracetamol, branch, counter, clinic, on_account):
    """A shop supplying two hospitals on 60-day terms may reasonably choose this. It is theirs."""
    settings.set_value("payments.over_limit_behaviour", "warn")

    invoice = a_bill(paracetamol, branch, counter, clinic)
    settle_invoice(invoice, tenders=[(on_account, invoice.payable_amount)])

    from core.payments.credit import outstanding_for

    assert outstanding_for(clinic) == Decimal("80.00")


def test_a_sale_allowed_only_by_a_warning_still_reads_as_one(clinic, branch):
    """It went through, but it should not look clean afterwards."""
    settings.set_value("payments.over_limit_behaviour", "warn")

    decision = assess(clinic, amount=Decimal("500"), on_date=TODAY, branch=branch)
    assert decision.allowed
    assert decision.is_warning
    assert "over the limit" in decision.reason


def test_one_branch_can_warn_while_another_blocks(paracetamol, branch, counter, clinic, on_account):
    settings.set_value("payments.over_limit_behaviour", "warn", scope=Scope.BRANCH, branch=branch)

    assert assess(clinic, amount=Decimal("500"), on_date=TODAY, branch=branch).allowed
    assert not assess(clinic, amount=Decimal("500"), on_date=TODAY).allowed


# --------------------------------------------------------------------------- grace days
def test_by_default_a_bill_is_overdue_the_day_after_it_is_due(
    paracetamol, branch, counter, clinic, on_account
):
    clinic.credit_limit = Decimal("5000")
    clinic.save(update_fields=["credit_limit", "updated_at"])
    old = a_bill(paracetamol, branch, counter, clinic, on_date=TODAY - timedelta(days=31))
    settle_invoice(old, tenders=[(on_account, old.payable_amount)])

    assert not assess(clinic, amount=Decimal("10"), on_date=TODAY, branch=branch).allowed


def test_a_few_days_of_grace_can_be_granted(paracetamol, branch, counter, clinic, on_account):
    """Blocking a customer at the counter over one day costs more than it saves."""
    clinic.credit_limit = Decimal("5000")
    clinic.save(update_fields=["credit_limit", "updated_at"])
    old = a_bill(paracetamol, branch, counter, clinic, on_date=TODAY - timedelta(days=31))
    settle_invoice(old, tenders=[(on_account, old.payable_amount)])

    settings.set_value("payments.overdue_grace_days", 7)
    assert assess(clinic, amount=Decimal("10"), on_date=TODAY, branch=branch).allowed


# --------------------------------------------------------------------------- the till
def test_the_variance_tolerance_can_be_widened(branch, counter, cashier):
    shift = open_shift(
        branch=branch,
        location=counter,
        cashier=cashier,
        opening_float=Decimal("2000"),
        business_date=TODAY,
    )
    settings.set_value("payments.till_variance_tolerance", Decimal("10"))

    closed = close_shift(shift, counts={1000: 1, 500: 1, 100: 4, 50: 1, 20: 2})
    assert closed.variance == Decimal("-10.00")
    assert closed.counted_cash == Decimal("1990.00")


def test_a_pharmacy_can_stand_down_the_witness_rule(branch, counter, cashier):
    """Theirs to decide, and the default is the strict one."""
    shift = open_shift(branch=branch, location=counter, cashier=cashier, business_date=TODAY)
    settings.set_value("payments.require_witness_for_cash_out", False)

    movement = pay_out(shift, amount=Decimal("100"), reason="Tea for the staff", witness_name="")
    assert movement.amount == Decimal("-100.00")


def test_the_witness_rule_is_on_unless_somebody_turns_it_off(branch, counter, cashier):
    shift = open_shift(branch=branch, location=counter, cashier=cashier, business_date=TODAY)
    with pytest.raises(DomainError) as caught:
        pay_out(shift, amount=Decimal("100"), reason="Tea", witness_name="")
    assert caught.value.error.code == "CASH_OUT_NEEDS_A_WITNESS"


def test_a_branch_can_have_its_own_opening_float(branch, counter, cashier):
    settings.set_value(
        "payments.default_opening_float", Decimal("3000"), scope=Scope.BRANCH, branch=branch
    )
    shift = open_shift(branch=branch, location=counter, cashier=cashier, business_date=TODAY)
    assert shift.opening_float == Decimal("3000.00")


def test_a_float_typed_in_still_wins_over_the_default(branch, counter, cashier):
    settings.set_value("payments.default_opening_float", Decimal("3000"))
    shift = open_shift(
        branch=branch,
        location=counter,
        cashier=cashier,
        opening_float=Decimal("500"),
        business_date=TODAY,
    )
    assert shift.opening_float == Decimal("500.00")
