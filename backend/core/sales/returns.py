"""Credit notes and sales returns.

A sale is never deleted and an issued invoice is never edited. IRD's rule, and a sound one: a bill
the customer is holding a copy of cannot quietly change. So the only way money comes back off a
bill is a credit note against it, numbered in its own series so the run can be inspected.

Three shapes, and they behave differently on purpose:

* **cancellation** — the whole invoice is undone. `cancel_invoice` reverses the stock itself, so
  the note is the tax evidence and moves nothing;
* **return** — goods came back over the counter. The note is what brings them into stock, and by
  default into quarantine rather than onto the shelf;
* **adjustment** — money only. An overcharge, or a discount agreed after the fact.

You cannot credit more than was sold. That is checked against the invoice line, counting what
earlier credit notes already took, so two half-returns cannot add up to more than the whole.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

import structlog
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from core.catalog.services import to_base
from core.inventory.models import MovementType, StockLedgerEntry
from core.inventory.services import post_movement
from kernel.audit import services as audit
from kernel.audit.models import AuditAction
from kernel.numbering.services import issue_number
from kernel.tenancy.models import Location
from shared.errors import DomainError
from shared.formatting import amount_in_words_en

from . import errors
from .document_types import CREDIT_NOTE
from .extensions import run_credit_note_hooks
from .models import (
    CreditNote,
    CreditNoteKind,
    CreditNoteLine,
    InvoiceStatus,
    ReturnDestination,
    ReturnReason,
    SalesInvoice,
    SalesInvoiceLine,
)
from .totals import DEFAULT_ROUNDING_STEP, LineAmounts, compute_line, compute_totals

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IssuedCreditNote:
    credit_note: CreditNote
    entries: list[StockLedgerEntry]

    @property
    def amount_in_words(self) -> str:
        return amount_in_words_en(self.credit_note.payable_amount)


# --------------------------------------------------------------------------- drafting
@transaction.atomic
def start_credit_note(
    invoice: SalesInvoice,
    *,
    reason: str,
    kind: str = CreditNoteKind.RETURN,
    reason_code: str = ReturnReason.OTHER,
    destination: str = ReturnDestination.QUARANTINE,
    location: Any = None,
    note_date: date | None = None,
) -> CreditNote:
    """Open a draft credit note against an issued invoice.

    A reason is required. A credit note with no stated reason is the shape a till is emptied in,
    and it is the first thing an inspection pulls.
    """
    if invoice.status == InvoiceStatus.DRAFT:
        raise DomainError(
            errors.CREDIT_NOTE_NEEDS_AN_ISSUED_INVOICE,
            "A draft bill has not been given to anybody. Change it instead of crediting it.",
        )
    if not reason.strip():
        raise DomainError(errors.CREDIT_NOTE_NEEDS_A_REASON)

    return cast(
        "CreditNote",
        CreditNote.objects.create(
            invoice=invoice,
            branch=invoice.branch,
            location=location or _destination_location(invoice, destination),
            kind=kind,
            reason_code=reason_code,
            reason=reason.strip(),
            destination=destination,
            note_date=note_date or invoice.invoice_date,
            prices_include_tax=invoice.prices_include_tax,
        ),
    )


def _destination_location(invoice: SalesInvoice, destination: str) -> Location:
    """Quarantine unless somebody decided otherwise.

    A medicine that has been out of the pharmacy comes back to quarantine, where a pharmacist
    looks at it before it is either put back or written off. Choosing the counter instead is a
    deliberate act for a sealed pack that never really left.
    """
    if destination == ReturnDestination.SELLABLE:
        return invoice.location
    quarantine = Location.objects.filter(
        branch=invoice.branch, is_sellable=False, is_active=True
    ).first()
    if quarantine is None:
        raise DomainError(
            errors.NO_QUARANTINE_LOCATION,
            "This branch has no quarantine location to return stock into.",
        )
    return cast("Location", quarantine)


@transaction.atomic
def add_return_line(
    credit_note: CreditNote,
    *,
    invoice_line: SalesInvoiceLine,
    quantity: Decimal | int | str,
    batch: Any = None,
) -> list[CreditNoteLine]:
    """Credit part or all of one invoice line.

    Returns a line per batch, because a single sale can have drawn on several. Which batch came
    back matters: putting a customer's return against the wrong lot makes the batch record — the
    thing a recall is answered from — say something untrue.
    """
    _require_editable(credit_note)
    if invoice_line.invoice_id != credit_note.invoice_id:
        raise DomainError(
            errors.CREDIT_LINE_IS_NOT_ON_THIS_INVOICE,
            "That line belongs to a different invoice.",
        )

    asked = Decimal(str(quantity))
    if asked <= 0:
        raise DomainError(errors.CREDIT_QUANTITY_MUST_BE_POSITIVE)

    remaining = creditable_quantity(invoice_line)
    if asked > remaining:
        raise DomainError(
            errors.CREDIT_EXCEEDS_WHAT_WAS_SOLD,
            f"{invoice_line.item.name}: {remaining} left to credit, not {asked}.",
        )

    created: list[CreditNoteLine] = []
    for allocation_batch, share in _split_across_batches(invoice_line, asked, batch=batch):
        line = cast(
            "CreditNoteLine",
            CreditNoteLine.objects.create(
                credit_note=credit_note,
                invoice_line=invoice_line,
                item=invoice_line.item,
                unit=invoice_line.unit,
                batch=allocation_batch,
                quantity=share,
                base_quantity=to_base(invoice_line.item, share, invoice_line.unit),
                rate=invoice_line.rate,
                discount_percent=invoice_line.discount_percent,
                tax_percentage=invoice_line.tax_percentage,
                unit_cost=_unit_cost_of(invoice_line, allocation_batch),
            ),
        )
        _apply_amounts(line, credit_note=credit_note)
        created.append(line)
    return created


def _split_across_batches(
    invoice_line: SalesInvoiceLine, asked: Decimal, *, batch: Any = None
) -> list[tuple[Any, Decimal]]:
    """Which batches this return comes out of, in the order they were sold.

    Naming a batch pins it to that one — the pack in the customer's hand has a number printed on
    it, and when somebody reads it, that is better evidence than any guess made here.
    """
    allocations = list(invoice_line.allocations.select_related("batch").order_by("created_at"))
    if not allocations:
        return [(None, asked)]

    already = _credited_per_batch(invoice_line)
    if batch is not None:
        return [(batch, asked)]

    shares: list[tuple[Any, Decimal]] = []
    left = asked
    for allocation in allocations:
        if left <= 0:
            break
        # Allocations are in base units; the credit is in the unit the customer bought.
        sold = _to_line_unit(invoice_line, allocation.quantity)
        available = sold - already.get(allocation.batch_id, Decimal("0"))
        if available <= 0:
            continue
        take = min(left, available)
        shares.append((allocation.batch, take))
        left -= take

    if left > 0:  # nothing left to pin it to, so it goes against the last batch sold
        shares.append((allocations[-1].batch, left))
    return shares


def _to_line_unit(invoice_line: SalesInvoiceLine, base_quantity: Decimal) -> Decimal:
    """Base units back into the pack the line was priced in."""
    if invoice_line.base_quantity == 0:
        return base_quantity
    return base_quantity * invoice_line.quantity / invoice_line.base_quantity


def _credited_per_batch(invoice_line: SalesInvoiceLine) -> dict[Any, Decimal]:
    rows = (
        CreditNoteLine.objects.filter(
            invoice_line=invoice_line, credit_note__status=InvoiceStatus.ISSUED
        )
        .values("batch_id")
        .annotate(total=Sum("quantity"))
    )
    return {row["batch_id"]: row["total"] or Decimal("0") for row in rows}


def _unit_cost_of(invoice_line: SalesInvoiceLine, batch: Any) -> Decimal:
    allocation = invoice_line.allocations.filter(batch=batch).first()
    return allocation.unit_cost if allocation else Decimal("0")


def creditable_quantity(invoice_line: SalesInvoiceLine) -> Decimal:
    """How much of this line has not been credited yet.

    Counts issued credit notes only. A draft is somebody's unfinished intention, and blocking a
    return because of a draft nobody completed would strand the customer at the counter.
    """
    credited = CreditNoteLine.objects.filter(
        invoice_line=invoice_line, credit_note__status=InvoiceStatus.ISSUED
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    return invoice_line.quantity - credited


def _apply_amounts(line: CreditNoteLine, *, credit_note: CreditNote) -> LineAmounts:
    amounts = compute_line(
        quantity=line.quantity,
        rate=line.rate,
        discount_percent=line.discount_percent,
        tax_percentage=line.tax_percentage,
        price_includes_tax=credit_note.prices_include_tax,
    )
    line.gross_amount = amounts.gross
    line.discount_amount = amounts.discount
    line.taxable_amount = amounts.taxable
    line.tax_amount = amounts.tax
    line.save(
        update_fields=[
            "gross_amount",
            "discount_amount",
            "taxable_amount",
            "tax_amount",
            "updated_at",
        ]
    )
    return amounts


def _require_editable(credit_note: CreditNote) -> None:
    if not credit_note.is_editable:
        raise DomainError(errors.CREDIT_NOTE_NOT_EDITABLE)


def recalculate(credit_note: CreditNote, *, rounding_step: Decimal = DEFAULT_ROUNDING_STEP) -> None:
    lines = list(credit_note.lines.all())
    amounts = [
        LineAmounts(
            gross=line.gross_amount,
            discount=line.discount_amount,
            net=line.gross_amount - line.discount_amount,
            taxable=line.taxable_amount,
            tax=line.tax_amount,
        )
        for line in lines
    ]
    totals = compute_totals(amounts, rounding_step=rounding_step)

    credit_note.gross_amount = totals.gross
    credit_note.discount_amount = totals.discount
    credit_note.taxable_amount = totals.taxable
    credit_note.tax_amount = totals.tax
    credit_note.rounding_amount = totals.rounding
    credit_note.payable_amount = totals.payable
    credit_note.save(
        update_fields=[
            "gross_amount",
            "discount_amount",
            "taxable_amount",
            "tax_amount",
            "rounding_amount",
            "payable_amount",
            "updated_at",
        ]
    )


# --------------------------------------------------------------------------- issuing
@transaction.atomic
def issue_credit_note(
    credit_note: CreditNote,
    *,
    actor: Any = None,
    rounding_step: Decimal = DEFAULT_ROUNDING_STEP,
) -> IssuedCreditNote:
    """Number it, bring the stock back if it is a return, and fix the totals.

    The number is taken first, so every stock movement carries it from the start — the ledger is
    append-only and there is no going back to fill it in. If anything fails the whole thing rolls
    back and the number is not consumed, which is what keeps the credit-note run gapless.
    """
    _require_editable(credit_note)
    lines = list(credit_note.lines.select_related("item", "unit", "batch").all())
    if not lines:
        raise DomainError(errors.CREDIT_NOTE_HAS_NO_LINES)

    issued = issue_number(
        document_type=CREDIT_NOTE, branch=credit_note.branch, on_date=credit_note.note_date
    )

    entries: list[StockLedgerEntry] = []
    if credit_note.moves_stock:
        for line in lines:
            entries.append(
                post_movement(
                    item=line.item,
                    branch=credit_note.branch,
                    location=credit_note.location,
                    batch=line.batch,
                    quantity=line.base_quantity,
                    movement_type=MovementType.SALE_RETURN,
                    unit_cost=line.unit_cost,
                    occurred_on=credit_note.note_date,
                    actor=actor,
                    document_type=CREDIT_NOTE,
                    document_id=str(credit_note.pk),
                    document_number=issued.number,
                    document_line_id=str(line.pk),
                )
            )

    recalculate(credit_note, rounding_step=rounding_step)
    credit_note.number = issued.number
    credit_note.fiscal_year = issued.fiscal_year
    credit_note.status = InvoiceStatus.ISSUED
    credit_note.issued_at = timezone.now()
    credit_note.save(update_fields=["number", "fiscal_year", "status", "issued_at", "updated_at"])

    audit.record(
        action=AuditAction.CREATE,
        actor=actor,
        entity=credit_note,
        entity_label=f"{issued.number} against {credit_note.invoice.number}",
        changes={
            "status": {"from": InvoiceStatus.DRAFT, "to": InvoiceStatus.ISSUED},
            "amount": {"from": None, "to": str(credit_note.payable_amount)},
        },
        reason=credit_note.reason,
        branch=credit_note.branch,
    )

    run_credit_note_hooks(credit_note, entries=entries, actor=actor)

    logger.info(
        "credit_note_issued",
        number=issued.number,
        invoice=credit_note.invoice.number,
        kind=credit_note.kind,
        amount=str(credit_note.payable_amount),
    )
    return IssuedCreditNote(credit_note=credit_note, entries=entries)


# --------------------------------------------------------------------------- the whole invoice
@transaction.atomic
def credit_whole_invoice(
    invoice: SalesInvoice,
    *,
    reason: str,
    kind: str = CreditNoteKind.CANCELLATION,
    reason_code: str = ReturnReason.INVOICE_CANCELLED,
    destination: str = ReturnDestination.QUARANTINE,
    actor: Any = None,
) -> IssuedCreditNote:
    """Credit every line of an invoice in full.

    What a cancellation issues. Because the lines are copied at the rates that were charged, the
    note comes to exactly what the invoice did — including the rounding, which recomputes the
    same way on the same numbers.
    """
    note = start_credit_note(
        invoice,
        reason=reason,
        kind=kind,
        reason_code=reason_code,
        destination=destination,
        location=None if kind == CreditNoteKind.RETURN else invoice.location,
    )
    for line in invoice.lines.select_related("item", "unit").all():
        remaining = creditable_quantity(line)
        if remaining > 0:
            add_return_line(note, invoice_line=line, quantity=remaining)
    return issue_credit_note(note, actor=actor)


def record_print(credit_note: CreditNote) -> int:
    """Count a print. Anything after the first is a copy and is marked as one."""
    CreditNote.objects.filter(pk=credit_note.pk).update(print_count=F("print_count") + 1)
    credit_note.refresh_from_db(fields=["print_count"])
    return credit_note.print_count


def is_copy(credit_note: CreditNote) -> bool:
    return credit_note.print_count > 1


def credit_notes_for(invoice: SalesInvoice) -> list[CreditNote]:
    return list(
        CreditNote.objects.filter(invoice=invoice, status=InvoiceStatus.ISSUED).order_by(
            "note_date", "created_at"
        )
    )


def credited_amount(invoice: SalesInvoice) -> Decimal:
    """How much of this invoice has been credited back."""
    return CreditNote.objects.filter(invoice=invoice, status=InvoiceStatus.ISSUED).aggregate(
        total=Sum("payable_amount")
    )["total"] or Decimal("0")
