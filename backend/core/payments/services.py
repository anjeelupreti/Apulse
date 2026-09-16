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
from shared.errors import DomainError
from shared.formatting import quantize_money

from . import errors
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
    opening_float: Decimal | int | str = Decimal("0"),
    business_date: date | None = None,
    note: str = "",
) -> CashierShift:
    """Open the till.

    One open shift per counter, enforced by the database. Two people working one drawer means a
    shortfall belongs to both of them, which in practice means neither is ever asked about it.
    """
    if CashierShift.objects.filter(location=location, status=ShiftStatus.OPEN).exists():
        raise DomainError(errors.SHIFT_ALREADY_OPEN)

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
) -> list[Payment]:
    """Settle a bill, possibly across several methods at once.

    Split tender is normal here: half in cash and half on a wallet, or a partial payment with the
    rest on account. The total is checked against what is still owed, so a fat-fingered second
    tender cannot quietly overpay a bill and leave the accounts holding money nobody claimed.
    """
    references = references or {}
    asked = sum((quantize_money(amount) for _mode, amount in tenders), start=Decimal("0.00"))
    outstanding = amount_outstanding(invoice)
    if asked > outstanding:
        raise DomainError(
            errors.PAYMENT_EXCEEDS_WHAT_IS_DUE,
            f"{outstanding} is outstanding on {invoice.number}, not {asked}.",
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
            )
        )
    return payments


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
    """What has been received against a bill, net of anything reversed."""
    rows = Payment.objects.filter(
        document_type=invoice._meta.label_lower, document_id=str(invoice.pk)
    )
    total = sum((payment.signed_amount for payment in rows), start=Decimal("0.00"))
    return quantize_money(total)


def refunded_amount(credit_note: Any) -> Decimal:
    rows = Payment.objects.filter(
        document_type=credit_note._meta.label_lower, document_id=str(credit_note.pk)
    )
    total = sum((-payment.signed_amount for payment in rows), start=Decimal("0.00"))
    return quantize_money(total)


def amount_outstanding(invoice: Any) -> Decimal:
    """What is still owed on a bill: the total, less what was paid, less what was credited back."""
    from core.sales.returns import credited_amount

    return quantize_money(invoice.payable_amount - paid_amount(invoice) - credited_amount(invoice))


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
    if moved < 0 and not witness_name.strip():
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

    if needs_explanation(variance) and not variance_reason.strip():
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
