"""Selling on account, and what a customer owes.

Credit is how a pharmacy keeps a hospital, a clinic or a regular family as a customer, and it is
also how it quietly goes broke. So an account sale is not simply a payment mode with no cash
behind it: it is a decision, checked against what the customer already owes and whether they have
paid the last lot, and it can only be waved through by somebody with the authority to wave it —
with their name and their reason on the record.

Two things are checked, and they are different questions. A **limit** asks how much exposure this
customer is allowed. **Overdue** asks whether they pay at all. A customer well inside their limit
who has not settled anything since Baisakh is the worse risk of the two.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

import structlog
from django.utils import timezone

from shared.errors import DomainError
from shared.formatting import quantize_money

from . import errors
from .models import Payment, PaymentDirection, PaymentModeKind

logger = structlog.get_logger(__name__)

#: How an unpaid bill is aged on a statement. The last bucket is open-ended.
AGEING_BUCKETS: tuple[int, ...] = (30, 60, 90)


@dataclass(frozen=True, slots=True)
class CreditDecision:
    """Whether this sale may go on account, and the figures behind the answer.

    Returned rather than raised, so the counter can be shown the position *before* the customer is
    told no — "you are 2,000 over and a bill from Shrawan is unpaid" is a conversation, and a bare
    refusal is not.
    """

    allowed: bool
    limit: Decimal
    exposure: Decimal
    requested: Decimal
    overdue_amount: Decimal
    oldest_overdue_days: int
    reason: str = ""

    @property
    def headroom(self) -> Decimal:
        return quantize_money(self.limit - self.exposure)

    @property
    def would_exceed_by(self) -> Decimal:
        return quantize_money(max(Decimal("0"), self.exposure + self.requested - self.limit))


def assess(
    party: Any, *, amount: Decimal | int | str, on_date: date | None = None
) -> CreditDecision:
    """Look at the customer's position without changing anything."""
    on_date = on_date or timezone.localdate()
    requested = quantize_money(amount)
    limit = quantize_money(party.credit_limit)
    exposure = outstanding_for(party)
    overdue = overdue_for(party, as_of=on_date)
    oldest = oldest_overdue_days(party, as_of=on_date)

    if limit <= 0:
        return CreditDecision(
            allowed=False,
            limit=limit,
            exposure=exposure,
            requested=requested,
            overdue_amount=overdue,
            oldest_overdue_days=oldest,
            reason=f"{party.name} has no credit limit set.",
        )
    if overdue > 0:
        return CreditDecision(
            allowed=False,
            limit=limit,
            exposure=exposure,
            requested=requested,
            overdue_amount=overdue,
            oldest_overdue_days=oldest,
            reason=f"{party.name} has {overdue} overdue, the oldest by {oldest} days.",
        )
    if exposure + requested > limit:
        return CreditDecision(
            allowed=False,
            limit=limit,
            exposure=exposure,
            requested=requested,
            overdue_amount=overdue,
            oldest_overdue_days=oldest,
            reason=(
                f"{party.name} owes {exposure} of a {limit} limit; "
                f"this would put them {quantize_money(exposure + requested - limit)} over."
            ),
        )
    return CreditDecision(
        allowed=True,
        limit=limit,
        exposure=exposure,
        requested=requested,
        overdue_amount=overdue,
        oldest_overdue_days=oldest,
    )


def enforce(
    party: Any,
    *,
    amount: Decimal | int | str,
    on_date: date | None = None,
    override_reason: str = "",
    override_by: Any = None,
) -> CreditDecision:
    """Check the decision and refuse unless somebody overrode it, by name and with a reason.

    An override with no name attached is the same as no control at all, and an override with no
    reason is worse than none: it looks like a control while teaching everybody that the box can
    be filled with anything.
    """
    if party is None:
        raise DomainError(errors.CREDIT_NEEDS_A_NAMED_CUSTOMER)

    decision = assess(party, amount=amount, on_date=on_date)
    if decision.allowed:
        return decision

    if not override_reason.strip():
        code = (
            errors.CUSTOMER_HAS_OVERDUE_BILLS
            if decision.overdue_amount > 0
            else errors.CREDIT_LIMIT_EXCEEDED
        )
        raise DomainError(code, decision.reason)
    if override_by is None:
        raise DomainError(errors.OVERRIDE_NEEDS_A_NAME)

    _record_override(party, decision, reason=override_reason, actor=override_by)
    return decision


def _record_override(party: Any, decision: CreditDecision, *, reason: str, actor: Any) -> None:
    from kernel.audit import services as audit
    from kernel.audit.models import AuditAction

    audit.record(
        action=AuditAction.OVERRIDE,
        actor=actor,
        entity=party,
        entity_label=party.name,
        changes={
            "credit_limit": {"from": str(decision.limit), "to": "overridden"},
            "exposure": {"from": None, "to": str(decision.exposure)},
            "requested": {"from": None, "to": str(decision.requested)},
            "overdue": {"from": None, "to": str(decision.overdue_amount)},
        },
        reason=reason,
    )
    logger.warning(
        "credit_override",
        party=party.name,
        exposure=str(decision.exposure),
        limit=str(decision.limit),
        reason=reason,
    )


# --------------------------------------------------------------------------- what they owe
def open_invoices(party: Any) -> list[Any]:
    """Issued bills for this customer that are not fully settled."""
    from core.payments.services import amount_outstanding
    from core.sales.models import InvoiceStatus, SalesInvoice

    invoices = SalesInvoice.objects.filter(customer=party, status=InvoiceStatus.ISSUED).order_by(
        "invoice_date", "created_at"
    )
    return [invoice for invoice in invoices if amount_outstanding(invoice) > 0]


def outstanding_for(party: Any) -> Decimal:
    """Everything this customer owes across every unsettled bill."""
    from core.payments.services import amount_outstanding

    total = sum(
        (amount_outstanding(invoice) for invoice in open_invoices(party)), start=Decimal("0.00")
    )
    return quantize_money(total)


def due_date_for(invoice: Any, *, party: Any = None) -> date:
    """When a credit bill falls due.

    Taken from the customer's terms **as they stood on the day**, and frozen onto the invoice, so
    that shortening a customer's terms next year does not retrospectively make last year's bills
    late.
    """
    if invoice.due_date:
        return cast("date", invoice.due_date)
    customer = party or invoice.customer
    days = customer.credit_days if customer else 0
    return cast("date", invoice.invoice_date) + timedelta(days=days)


def overdue_for(party: Any, *, as_of: date | None = None) -> Decimal:
    from core.payments.services import amount_outstanding

    as_of = as_of or timezone.localdate()
    total = sum(
        (
            amount_outstanding(invoice)
            for invoice in open_invoices(party)
            if due_date_for(invoice, party=party) < as_of
        ),
        start=Decimal("0.00"),
    )
    return quantize_money(total)


def oldest_overdue_days(party: Any, *, as_of: date | None = None) -> int:
    as_of = as_of or timezone.localdate()
    overdue = [
        (as_of - due_date_for(invoice, party=party)).days
        for invoice in open_invoices(party)
        if due_date_for(invoice, party=party) < as_of
    ]
    return max(overdue) if overdue else 0


def ageing(party: Any, *, as_of: date | None = None) -> dict[str, Decimal]:
    """What is owed, split by how long it has been owed.

    The shape every collections conversation takes: not "they owe 40,000" but "30,000 of it has
    been sitting since Ashadh".
    """
    from core.payments.services import amount_outstanding

    as_of = as_of or timezone.localdate()
    buckets: dict[str, Decimal] = {"current": Decimal("0.00")}
    previous = 0
    for edge in AGEING_BUCKETS:
        buckets[f"{previous + 1}-{edge}"] = Decimal("0.00")
        previous = edge
    buckets[f"{previous}+"] = Decimal("0.00")

    for invoice in open_invoices(party):
        owed = amount_outstanding(invoice)
        overdue_days = (as_of - due_date_for(invoice, party=party)).days
        buckets[_bucket_for(overdue_days)] += owed

    return {name: quantize_money(value) for name, value in buckets.items()}


def _bucket_for(overdue_days: int) -> str:
    if overdue_days <= 0:
        return "current"
    previous = 0
    for edge in AGEING_BUCKETS:
        if overdue_days <= edge:
            return f"{previous + 1}-{edge}"
        previous = edge
    return f"{previous}+"


# --------------------------------------------------------------------------- the statement
@dataclass(frozen=True, slots=True)
class StatementLine:
    on_date: date
    kind: str
    reference: str
    description: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


def statement(party: Any, *, start: date, end: date) -> list[StatementLine]:
    """A customer's account as a running balance, the way they expect to be shown it.

    Bills are debits, payments and credit notes are credits, and the balance carried at the bottom
    is what the collections call is about. Ordered by business date rather than by when a row was
    written, because that is the order the customer's own file is in.
    """
    from core.sales.models import CreditNote, InvoiceStatus, SalesInvoice

    rows: list[tuple[date, str, str, str, Decimal, Decimal]] = []

    for invoice in SalesInvoice.objects.filter(
        customer=party,
        status=InvoiceStatus.ISSUED,
        invoice_date__gte=start,
        invoice_date__lte=end,
    ):
        rows.append(
            (
                invoice.invoice_date,
                "invoice",
                invoice.number,
                "Tax invoice",
                quantize_money(invoice.payable_amount),
                Decimal("0.00"),
            )
        )

    for note in CreditNote.objects.filter(
        invoice__customer=party,
        status=InvoiceStatus.ISSUED,
        note_date__gte=start,
        note_date__lte=end,
    ):
        rows.append(
            (
                note.note_date,
                "credit_note",
                note.number,
                note.reason or "Credit note",
                Decimal("0.00"),
                quantize_money(note.payable_amount),
            )
        )

    # An "on account" tender is left off: it is how the bill was settled at the counter, not
    # money arriving, and showing it as a credit would zero the very balance being chased.
    for payment in (
        Payment.objects.filter(party=party, received_on__gte=start, received_on__lte=end)
        .exclude(mode__kind=PaymentModeKind.CREDIT)
        .select_related("mode")
    ):
        received = payment.direction == PaymentDirection.IN
        rows.append(
            (
                payment.received_on,
                "payment",
                payment.reference or payment.document_number,
                f"{'Received' if received else 'Refunded'} — {payment.mode.name}",
                Decimal("0.00") if received else quantize_money(payment.amount),
                quantize_money(payment.amount) if received else Decimal("0.00"),
            )
        )

    rows.sort(key=lambda row: (row[0], row[1]))

    lines: list[StatementLine] = []
    balance = opening_balance(party, before=start)
    for on_date, kind, reference, description, debit, credit in rows:
        balance = quantize_money(balance + debit - credit)
        lines.append(
            StatementLine(
                on_date=on_date,
                kind=kind,
                reference=reference,
                description=description,
                debit=debit,
                credit=credit,
                balance=balance,
            )
        )
    return lines


def opening_balance(party: Any, *, before: date) -> Decimal:
    """What was owed the day before the statement starts."""
    from core.sales.models import CreditNote, InvoiceStatus, SalesInvoice

    billed = SalesInvoice.objects.filter(
        customer=party, status=InvoiceStatus.ISSUED, invoice_date__lt=before
    ).values_list("payable_amount", flat=True)
    credited = CreditNote.objects.filter(
        invoice__customer=party, status=InvoiceStatus.ISSUED, note_date__lt=before
    ).values_list("payable_amount", flat=True)
    paid = Payment.objects.filter(party=party, received_on__lt=before).exclude(
        mode__kind=PaymentModeKind.CREDIT
    )

    total = sum(billed, Decimal("0.00")) - sum(credited, Decimal("0.00"))
    total -= sum((payment.signed_amount for payment in paid), Decimal("0.00"))
    return quantize_money(total)
