"""Taking money, giving it back, and counting the drawer at the end of the shift."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

import structlog
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from kernel.audit import services as audit
from kernel.audit import tracking
from kernel.audit.models import AuditAction
from kernel.settings import services as settings
from shared.errors import DomainError
from shared.formatting import quantize_money

from . import credit, errors
from .denominations import count_total, needs_explanation, unknown_values
from .models import (
    CashierShift,
    CashMovement,
    CashMovementKind,
    DenominationCount,
    Payment,
    PaymentDirection,
    PaymentMode,
    PaymentModeKind,
    ShiftStatus,
)

logger = structlog.get_logger(__name__)

#: The modes every pharmacy starts with. A tenant adds or disables from here; nothing is forced.
DEFAULT_MODES: tuple[dict[str, Any], ...] = (
    {
        "code": "cash",
        "name": "Cash",
        "name_ne": "नगद",
        "kind": PaymentModeKind.CASH,
        "gives_change": True,
        "sort_order": 10,
    },
    {
        "code": "fonepay",
        "name": "Fonepay QR",
        "name_ne": "फोनपे",
        "kind": PaymentModeKind.QR,
        "requires_reference": True,
        "sort_order": 20,
    },
    {
        "code": "esewa",
        "name": "eSewa",
        "name_ne": "इसेवा",
        "kind": PaymentModeKind.WALLET,
        "requires_reference": True,
        "sort_order": 30,
    },
    {
        "code": "khalti",
        "name": "Khalti",
        "name_ne": "खल्ती",
        "kind": PaymentModeKind.WALLET,
        "requires_reference": True,
        "sort_order": 40,
    },
    {
        "code": "card",
        "name": "Card",
        "name_ne": "कार्ड",
        "kind": PaymentModeKind.CARD,
        "requires_reference": True,
        "sort_order": 50,
    },
    {
        "code": "bank",
        "name": "Bank transfer",
        "name_ne": "बैंक",
        "kind": PaymentModeKind.BANK_TRANSFER,
        "requires_reference": True,
        "sort_order": 60,
    },
    {
        "code": "cheque",
        "name": "Cheque",
        "name_ne": "चेक",
        "kind": PaymentModeKind.CHEQUE,
        "requires_reference": True,
        "sort_order": 70,
    },
    {
        "code": "credit",
        "name": "On account",
        "name_ne": "उधारो",
        "kind": PaymentModeKind.CREDIT,
        "sort_order": 80,
    },
)


@transaction.atomic
def install_default_modes() -> int:
    """Give a new pharmacy something to press on day one. Existing rows are left alone."""
    created = 0
    for mode in DEFAULT_MODES:
        _, was_created = PaymentMode.objects.get_or_create(
            code=mode["code"],
            defaults={key: value for key, value in mode.items() if key != "code"},
        )
        created += int(was_created)
    return created


# --------------------------------------------------------------------------- the shift
@transaction.atomic
def open_shift(
    *,
    branch: Any,
    location: Any,
    cashier: Any,
    opening_float: Decimal | int | str | None = None,
    business_date: date | None = None,
    note: str = "",
) -> CashierShift:
    """Open the till.

    One open shift per counter, enforced by the database. Two people working one drawer means a
    shortfall belongs to both of them, which in practice means neither is ever asked about it.

    The float falls back to whatever this branch normally starts with, so the usual case is one
    button and the unusual one is still typed in.
    """
    if CashierShift.objects.filter(location=location, status=ShiftStatus.OPEN).exists():
        raise DomainError(errors.SHIFT_ALREADY_OPEN)

    if opening_float is None:
        opening_float = settings.get_decimal("payments.default_opening_float", branch=branch)

    shift = cast(
        "CashierShift",
        CashierShift.objects.create(
            branch=branch,
            location=location,
            cashier=cashier,
            business_date=business_date or timezone.localdate(),
            opened_at=timezone.now(),
            opening_float=quantize_money(opening_float),
            note=note,
        ),
    )
    logger.info("shift_opened", shift=str(shift.pk), cashier=str(cashier), float=str(opening_float))
    return shift


def open_shift_for(location: Any) -> CashierShift | None:
    return CashierShift.objects.filter(location=location, status=ShiftStatus.OPEN).first()


def require_open_shift(location: Any) -> CashierShift:
    shift = open_shift_for(location)
    if shift is None:
        raise DomainError(errors.NO_OPEN_SHIFT)
    return shift


# --------------------------------------------------------------------------- taking money
@transaction.atomic
def record_payment(
    *,
    branch: Any,
    mode: PaymentMode,
    amount: Decimal | int | str,
    direction: str = PaymentDirection.IN,
    shift: CashierShift | None = None,
    tendered: Decimal | int | str | None = None,
    document_type: str = "",
    document_id: str = "",
    document_number: str = "",
    party: Any = None,
    reference: str = "",
    received_on: date | None = None,
    actor: Any = None,
    reason: str = "",
    note: str = "",
    override_reason: str = "",
    override_by: Any = None,
) -> Payment:
    """Record one movement of money, and work out the change if there is any.

    Change comes only out of cash. Handing change back on a card payment is one of the simplest
    ways to empty a till, and it is refused rather than warned about.
    """
    due = quantize_money(amount)
    if due <= 0:
        raise DomainError(errors.PAYMENT_MUST_BE_POSITIVE)
    if mode.requires_reference and not reference.strip():
        raise DomainError(
            errors.REFERENCE_REQUIRED, f"{mode.name} needs its transaction reference."
        )

    handed_over = quantize_money(tendered) if tendered is not None else due
    change = Decimal("0.00")
    if handed_over != due:
        if not mode.gives_change:
            raise DomainError(
                errors.CHANGE_ONLY_FROM_CASH,
                f"{mode.name} cannot give change; take the exact amount.",
            )
        if handed_over < due:
            raise DomainError(errors.NOT_ENOUGH_TENDERED)
        change = handed_over - due

    if mode.kind == PaymentModeKind.CREDIT:
        # An account sale is a decision, not a payment method with no cash behind it.
        credit.enforce(
            party,
            amount=due,
            on_date=received_on or timezone.localdate(),
            branch=branch,
            override_reason=override_reason,
            override_by=override_by or actor,
        )

    if shift is None and mode.kind == PaymentModeKind.CASH:
        # Cash has to belong to a drawer somebody is answerable for. Anything else can be
        # reconciled against a statement later, so it does not.
        raise DomainError(errors.NO_OPEN_SHIFT)

    payment = cast(
        "Payment",
        Payment.objects.create(
            branch=branch,
            shift=shift,
            mode=mode,
            direction=direction,
            amount=due,
            tendered_amount=handed_over,
            change_amount=change,
            document_type=document_type,
            document_id=document_id,
            document_number=document_number,
            party=party,
            reference=reference.strip(),
            received_on=received_on or timezone.localdate(),
            received_by=actor,
            reason=reason,
            note=note,
        ),
    )
    logger.info(
        "payment_recorded",
        direction=direction,
        mode=mode.code,
        amount=str(due),
        document=document_number,
    )
    return payment


@transaction.atomic
def settle_invoice(
    invoice: Any,
    *,
    tenders: list[tuple[PaymentMode, Decimal | int | str]],
    shift: CashierShift | None = None,
    tendered_cash: Decimal | int | str | None = None,
    references: Mapping[str, str] | None = None,
    actor: Any = None,
    override_reason: str = "",
    override_by: Any = None,
) -> list[Payment]:
    """Settle a bill, possibly across several methods at once.

    Split tender is normal here: half in cash and half on a wallet, or a partial payment with the
    rest on account. The total is checked against what is still owed, so a fat-fingered second
    tender cannot quietly overpay a bill and leave the accounts holding money nobody claimed.
    """
    references = references or {}
    asked = sum((quantize_money(amount) for _mode, amount in tenders), start=Decimal("0.00"))
    untendered = amount_untendered(invoice)
    if asked > untendered:
        raise DomainError(
            errors.PAYMENT_EXCEEDS_WHAT_IS_DUE,
            f"{untendered} is left to settle on {invoice.number}, not {asked}.",
        )

    payments = []
    for mode, amount in tenders:
        payments.append(
            record_payment(
                branch=invoice.branch,
                shift=shift,
                mode=mode,
                amount=amount,
                tendered=tendered_cash if mode.kind == PaymentModeKind.CASH else None,
                document_type=invoice._meta.label_lower,
                document_id=str(invoice.pk),
                document_number=invoice.number,
                party=invoice.customer,
                reference=references.get(mode.code, ""),
                received_on=invoice.invoice_date,
                actor=actor,
                override_reason=override_reason,
                override_by=override_by,
            )
        )
        if mode.kind == PaymentModeKind.CREDIT:
            _freeze_due_date(invoice)
    return payments


def _freeze_due_date(invoice: Any) -> None:
    """Write the due date onto the bill the moment it becomes a credit sale.

    Derived from the customer's terms as they stand today and then left alone. Recomputing it on
    every read would mean that tightening a customer's terms silently turned last year's settled
    history into a list of late payments.
    """
    if invoice.due_date is not None:
        return
    with tracking.paused():
        invoice.due_date = credit.due_date_for(invoice)
        invoice.save(update_fields=["due_date", "updated_at"])


@transaction.atomic
def receive_against(
    invoice: Any,
    *,
    mode: PaymentMode,
    amount: Decimal | int | str,
    shift: CashierShift | None = None,
    reference: str = "",
    received_on: date | None = None,
    actor: Any = None,
    note: str = "",
) -> Payment:
    """Take money against a bill that is already outstanding.

    A different act from settling at the counter, and the difference matters. `settle_invoice`
    covers the tenders that make up the bill while the customer is standing there — including
    putting it on account, which settles nothing and is meant not to. This is the cheque the
    clinic sends the following month, and it is checked against **what is still owed** rather than
    against what is left to tender, because the bill was fully tendered the day it was written.
    """
    asked = quantize_money(amount)
    outstanding = amount_outstanding(invoice)
    if asked > outstanding:
        raise DomainError(
            errors.PAYMENT_EXCEEDS_WHAT_IS_DUE,
            f"{outstanding} is outstanding on {invoice.number}, not {asked}.",
        )

    return record_payment(
        branch=invoice.branch,
        shift=shift,
        mode=mode,
        amount=asked,
        document_type=invoice._meta.label_lower,
        document_id=str(invoice.pk),
        document_number=invoice.number,
        party=invoice.customer,
        reference=reference,
        received_on=received_on,
        actor=actor,
        note=note,
    )


@transaction.atomic
def refund(
    credit_note: Any,
    *,
    mode: PaymentMode,
    amount: Decimal | int | str | None = None,
    shift: CashierShift | None = None,
    reference: str = "",
    actor: Any = None,
) -> Payment:
    """Give money back against a credit note.

    Against the note rather than the invoice on purpose: the note is the document that says money
    is owed back, and a refund with nothing behind it is indistinguishable from a till being
    emptied.
    """
    owed = quantize_money(amount) if amount is not None else credit_note.payable_amount
    already = refunded_amount(credit_note)
    if owed > credit_note.payable_amount - already:
        raise DomainError(
            errors.PAYMENT_EXCEEDS_WHAT_IS_DUE,
            f"{credit_note.payable_amount - already} is left to refund on {credit_note.number}.",
        )

    return record_payment(
        branch=credit_note.branch,
        shift=shift,
        mode=mode,
        amount=owed,
        direction=PaymentDirection.OUT,
        document_type=credit_note._meta.label_lower,
        document_id=str(credit_note.pk),
        document_number=credit_note.number,
        party=credit_note.invoice.customer,
        reference=reference,
        received_on=credit_note.note_date,
        actor=actor,
        reason=credit_note.reason,
    )


@transaction.atomic
def reverse_payment(payment: Payment, *, reason: str, actor: Any = None) -> Payment:
    """Undo a payment by recording its opposite. The original stays exactly as it was."""
    if payment.reversed_by.exists():
        raise DomainError(errors.PAYMENT_ALREADY_REVERSED)
    if not reason.strip():
        raise DomainError(errors.CASH_MOVEMENT_NEEDS_A_REASON)

    opposite = (
        PaymentDirection.OUT if payment.direction == PaymentDirection.IN else PaymentDirection.IN
    )
    reversal = cast(
        "Payment",
        Payment.objects.create(
            branch=payment.branch,
            shift=payment.shift,
            mode=payment.mode,
            direction=opposite,
            amount=payment.amount,
            tendered_amount=payment.amount,
            document_type=payment.document_type,
            document_id=payment.document_id,
            document_number=payment.document_number,
            party=payment.party,
            reference=payment.reference,
            received_on=payment.received_on,
            received_by=actor,
            reverses=payment,
            reason=reason,
        ),
    )
    audit.record(
        action=AuditAction.VOID,
        actor=actor,
        entity=payment,
        entity_label=f"{payment.amount} {payment.mode.name}",
        changes={"reversed": {"from": False, "to": True}},
        reason=reason,
        branch=payment.branch,
    )
    return reversal


# --------------------------------------------------------------------------- what is still owed
def paid_amount(invoice: Any) -> Decimal:
    """Money actually received against a bill, net of anything reversed.

    An "on account" tender is deliberately **not** counted. Putting a bill on account records how
    it was settled at the counter, not that the money arrived — treating it as received is how a
    receivables ledger comes to show nothing outstanding while the shop is owed a fortune.
    """
    rows = _payments_for(invoice).exclude(mode__kind=PaymentModeKind.CREDIT)
    return quantize_money(sum((payment.signed_amount for payment in rows), start=Decimal("0.00")))


def tendered_amount(invoice: Any) -> Decimal:
    """Everything put against the bill at the counter, including what went on account.

    What the overpay guard compares to. Without it a bill could be put on account twice over and
    each tender would look allowable, because neither had brought in any money to notice.
    """
    rows = _payments_for(invoice)
    return quantize_money(sum((payment.signed_amount for payment in rows), start=Decimal("0.00")))


def _payments_for(document: Any) -> Any:
    return Payment.objects.filter(
        document_type=document._meta.label_lower, document_id=str(document.pk)
    ).select_related("mode")


def refunded_amount(credit_note: Any) -> Decimal:
    rows = _payments_for(credit_note)
    total = sum((-payment.signed_amount for payment in rows), start=Decimal("0.00"))
    return quantize_money(total)


def amount_outstanding(invoice: Any) -> Decimal:
    """What the customer still owes: the total, less money received, less what was credited back.

    A bill put on account is fully outstanding until it is actually paid, which is the whole point
    of the arrangement.
    """
    from core.sales.returns import credited_amount

    return quantize_money(invoice.payable_amount - paid_amount(invoice) - credited_amount(invoice))


def amount_untendered(invoice: Any) -> Decimal:
    """What still needs a tender at the counter before the customer can leave."""
    from core.sales.returns import credited_amount

    return quantize_money(
        invoice.payable_amount - tendered_amount(invoice) - credited_amount(invoice)
    )


def is_settled(invoice: Any) -> bool:
    return amount_outstanding(invoice) <= 0


# --------------------------------------------------------------------------- the drawer
@transaction.atomic
def record_cash_movement(
    shift: CashierShift,
    *,
    kind: str,
    amount: Decimal | int | str,
    reason: str,
    witness_name: str = "",
    reference: str = "",
    actor: Any = None,
) -> CashMovement:
    """Cash into or out of the drawer for something that is not a sale.

    Money leaving needs a witness. One person alone deciding that six hundred rupees left the till
    for a taxi is not a control, it is a description of how a till is emptied.
    """
    moved = quantize_money(amount)
    if moved == 0:
        raise DomainError(errors.PAYMENT_MUST_BE_POSITIVE)
    if not reason.strip():
        raise DomainError(errors.CASH_MOVEMENT_NEEDS_A_REASON)
    needs_witness = settings.get_bool("payments.require_witness_for_cash_out", branch=shift.branch)
    if moved < 0 and needs_witness and not witness_name.strip():
        raise DomainError(errors.CASH_OUT_NEEDS_A_WITNESS)
    _require_open(shift)

    return cast(
        "CashMovement",
        CashMovement.objects.create(
            shift=shift,
            kind=kind,
            amount=moved,
            reason=reason.strip(),
            reference=reference,
            recorded_by=actor,
            witness_name=witness_name.strip(),
        ),
    )


def pay_out(
    shift: CashierShift,
    *,
    amount: Decimal | int | str,
    reason: str,
    witness_name: str,
    actor: Any = None,
) -> CashMovement:
    """A petty expense paid out of the till."""
    return record_cash_movement(
        shift,
        kind=CashMovementKind.PETTY_EXPENSE,
        amount=-abs(quantize_money(amount)),
        reason=reason,
        witness_name=witness_name,
        actor=actor,
    )


def _require_open(shift: CashierShift) -> None:
    if not shift.is_open:
        raise DomainError(errors.SHIFT_ALREADY_CLOSED)


# --------------------------------------------------------------------------- counting it out
@dataclass(frozen=True, slots=True)
class ShiftSummary:
    """What the Z-report prints, and what the close is checked against."""

    opening_float: Decimal
    cash_received: Decimal
    cash_refunded: Decimal
    cash_movements: Decimal
    expected_cash: Decimal
    by_mode: dict[str, Decimal]
    payment_count: int

    @property
    def cash_taken(self) -> Decimal:
        return self.cash_received - self.cash_refunded


def summarise(shift: CashierShift) -> ShiftSummary:
    """Add up the shift: what came in, by which method, and what the drawer should hold.

    Change is not subtracted anywhere. A hundred-rupee note handed over for a sixty-rupee bill
    leaves sixty in the drawer, and sixty is what the payment records — the forty going back is
    not a separate movement of the shop's money.
    """
    payments = list(shift.payments.select_related("mode").all())

    by_mode: dict[str, Decimal] = {}
    cash_received = Decimal("0.00")
    cash_refunded = Decimal("0.00")
    for payment in payments:
        by_mode[payment.mode.code] = by_mode.get(payment.mode.code, Decimal("0.00")) + (
            payment.signed_amount
        )
        if payment.mode.kind == PaymentModeKind.CASH:
            if payment.direction == PaymentDirection.IN:
                cash_received += payment.amount
            else:
                cash_refunded += payment.amount

    movements = shift.cash_movements.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    expected = shift.opening_float + cash_received - cash_refunded + movements

    return ShiftSummary(
        opening_float=quantize_money(shift.opening_float),
        cash_received=quantize_money(cash_received),
        cash_refunded=quantize_money(cash_refunded),
        cash_movements=quantize_money(movements),
        expected_cash=quantize_money(expected),
        by_mode={code: quantize_money(total) for code, total in by_mode.items()},
        payment_count=len(payments),
    )


@transaction.atomic
def close_shift(
    shift: CashierShift,
    *,
    counts: Mapping[int, int],
    actor: Any = None,
    variance_reason: str = "",
    note: str = "",
) -> CashierShift:
    """Count the drawer and close the till.

    The count is taken as given and the difference is recorded. It is never adjusted to match the
    register: a drawer that is short by four hundred rupees is a fact about the day, and a system
    that quietly writes it off destroys the only signal anybody had.

    A difference beyond a rupee needs an explanation before the shift will close.
    """
    _require_open(shift)

    unknown = unknown_values(counts)
    if unknown:
        raise DomainError(
            errors.UNKNOWN_DENOMINATION,
            f"{', '.join(str(value) for value in unknown)} is not a Nepali note or coin.",
        )

    summary = summarise(shift)
    counted = count_total(counts)
    variance = counted - summary.expected_cash
    tolerance = settings.get_decimal("payments.till_variance_tolerance", branch=shift.branch)

    if needs_explanation(variance, tolerance=tolerance) and not variance_reason.strip():
        raise DomainError(
            errors.VARIANCE_NEEDS_AN_EXPLANATION,
            f"The drawer is {'over' if variance > 0 else 'short'} by {abs(variance)}.",
        )

    DenominationCount.objects.filter(shift=shift).delete()
    DenominationCount.objects.bulk_create(
        [
            DenominationCount(tenant_id=shift.tenant_id, shift=shift, value=value, count=count)
            for value, count in sorted(counts.items(), reverse=True)
            if count
        ]
    )

    with tracking.paused():
        shift.status = ShiftStatus.CLOSED
        shift.closed_at = timezone.now()
        shift.closed_by = actor
        shift.expected_cash = summary.expected_cash
        shift.counted_cash = counted
        shift.variance = variance
        shift.variance_reason = variance_reason.strip()
        shift.note = note or shift.note
        shift.save(
            update_fields=[
                "status",
                "closed_at",
                "closed_by",
                "expected_cash",
                "counted_cash",
                "variance",
                "variance_reason",
                "note",
                "updated_at",
            ]
        )

    audit.record(
        action=AuditAction.UPDATE,
        actor=actor,
        entity=shift,
        entity_label=f"Till at {shift.location} on {shift.business_date}",
        changes={
            "status": {"from": ShiftStatus.OPEN, "to": ShiftStatus.CLOSED},
            "expected_cash": {"from": None, "to": str(summary.expected_cash)},
            "counted_cash": {"from": None, "to": str(counted)},
            "variance": {"from": None, "to": str(variance)},
        },
        reason=variance_reason,
        branch=shift.branch,
    )
    logger.info(
        "shift_closed",
        shift=str(shift.pk),
        expected=str(summary.expected_cash),
        counted=str(counted),
        variance=str(variance),
    )
    return shift


@transaction.atomic
def approve_shift(shift: CashierShift, *, approver: Any, note: str = "") -> CashierShift:
    """A supervisor signs off a closed till.

    Separate from closing, and by somebody else: a cashier counting their own drawer and approving
    their own count is one person, not two, however many buttons they press.
    """
    if shift.is_open:
        raise DomainError(errors.SHIFT_ALREADY_CLOSED, "Close the till before approving it.")

    with tracking.paused():
        shift.approved_by = approver
        shift.approved_at = timezone.now()
        shift.note = note or shift.note
        shift.save(update_fields=["approved_by", "approved_at", "note", "updated_at"])

    audit.record(
        action=AuditAction.UPDATE,
        actor=approver,
        entity=shift,
        entity_label=f"Till at {shift.location} on {shift.business_date}",
        changes={"approved_by": {"from": None, "to": str(approver)}},
        reason=note,
        branch=shift.branch,
    )
    return shift
