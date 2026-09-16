"""Building a bill and issuing it."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

import structlog
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.catalog.models import Item, ItemUnit, UnitOfMeasure
from core.catalog.services import to_base, validate_quantity
from core.inventory.models import MovementType, StockBalance, StockLedgerEntry
from core.inventory.services import allocate_fefo, post_movement, reverse_movement
from kernel.audit import services as audit
from kernel.audit.models import AuditAction
from kernel.numbering.services import issue_number
from shared.errors import DomainError
from shared.formatting import amount_in_words_en

from . import errors
from .document_types import SALES_INVOICE
from .models import (
    InvoiceStatus,
    SalesInvoice,
    SalesInvoiceLine,
    SalesInvoiceLineBatch,
)
from .totals import DEFAULT_ROUNDING_STEP, LineAmounts, compute_line, compute_totals

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IssuedInvoice:
    invoice: SalesInvoice
    entries: list[StockLedgerEntry]

    @property
    def amount_in_words(self) -> str:
        return amount_in_words_en(self.invoice.payable_amount)


# --------------------------------------------------------------------------- building the bill
@transaction.atomic
def start_invoice(
    *,
    branch: Any,
    location: Any,
    invoice_date: date | None = None,
    customer: Any = None,
    customer_name: str = "",
    customer_phone: str = "",
    prices_include_tax: bool = True,
) -> SalesInvoice:
    return cast(
        "SalesInvoice",
        SalesInvoice.objects.create(
            branch=branch,
            location=location,
            invoice_date=invoice_date or timezone.localdate(),
            customer=customer,
            customer_name=customer_name or (customer.name if customer else ""),
            customer_phone=customer_phone or (customer.phone if customer else ""),
            prices_include_tax=prices_include_tax,
        ),
    )


@transaction.atomic
def add_line(
    invoice: SalesInvoice,
    *,
    item: Item,
    quantity: Decimal | int | str,
    unit: UnitOfMeasure | None = None,
    rate: Decimal | int | str | None = None,
    discount_percent: Decimal | int | str = Decimal("0"),
) -> SalesInvoiceLine:
    """Add an item to the bill, priced at the printed price unless told otherwise."""
    _require_editable(invoice)

    if unit is None:
        default = ItemUnit.objects.filter(item=item, is_sale_default=True).first()
        unit = default.unit if default else item.base_unit

    base_quantity = to_base(item, quantity, unit)
    validate_quantity(item, base_quantity, unit=unit)

    rate_value = (
        Decimal(str(rate))
        if rate is not None
        else _printed_price(item, unit=unit, branch=invoice.branch)
    )
    _refuse_above_mrp(item, unit=unit, branch=invoice.branch, rate=rate_value)

    line = cast(
        "SalesInvoiceLine",
        SalesInvoiceLine.objects.create(
            invoice=invoice,
            item=item,
            unit=unit,
            quantity=Decimal(str(quantity)),
            base_quantity=base_quantity,
            rate=rate_value,
            discount_percent=Decimal(str(discount_percent)),
            tax_percentage=item.tax_category.rate_on(invoice.invoice_date),
        ),
    )
    _apply_amounts(line, invoice=invoice)
    return line


def _pack_factor(item: Item, unit: UnitOfMeasure) -> Decimal:
    pack = ItemUnit.objects.filter(item=item, unit=unit).first()
    return pack.factor if pack else Decimal("1")


def _mrp_per_base_unit(item: Item, *, branch: Any) -> Decimal | None:
    """The printed price of the stock actually on the shelf, nearest expiry first.

    The batch wins over the item, because two lots of the same medicine can carry different
    printed prices and the customer is holding one of them. Goods that are not batch-tracked fall
    back to the item's own price.
    """
    balances = (
        StockBalance.objects.filter(item=item, branch=branch, quantity__gt=0)
        .select_related("batch")
        .order_by("batch__expiry_date")
    )
    for balance in balances:
        if balance.batch is not None and balance.batch.mrp:
            return cast("Decimal", balance.batch.mrp)
    return item.mrp or None


def _printed_price(item: Item, *, unit: UnitOfMeasure, branch: Any) -> Decimal:
    mrp = _mrp_per_base_unit(item, branch=branch)
    if mrp is None:
        raise DomainError(errors.NO_PRICE_SET, f"{item.name} has no printed price recorded.")
    return mrp * _pack_factor(item, unit)


def _refuse_above_mrp(item: Item, *, unit: UnitOfMeasure, branch: Any, rate: Decimal) -> None:
    """Selling above the printed maximum retail price is an offence, so it is refused."""
    mrp = _mrp_per_base_unit(item, branch=branch)
    if mrp is None:
        return
    ceiling = mrp * _pack_factor(item, unit)
    if rate > ceiling:
        raise DomainError(
            errors.PRICE_ABOVE_MRP,
            f"{item.name}: the printed maximum is {ceiling} per {unit.name.lower()}.",
        )


def _apply_amounts(line: SalesInvoiceLine, *, invoice: SalesInvoice) -> LineAmounts:
    amounts = compute_line(
        quantity=line.quantity,
        rate=line.rate,
        discount_percent=line.discount_percent,
        tax_percentage=line.tax_percentage,
        price_includes_tax=invoice.prices_include_tax,
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


def _require_editable(invoice: SalesInvoice) -> None:
    if not invoice.is_editable:
        raise DomainError(errors.INVOICE_NOT_EDITABLE)


def recalculate(invoice: SalesInvoice, *, rounding_step: Decimal = DEFAULT_ROUNDING_STEP) -> None:
    """Refresh the invoice totals from its lines, without issuing it."""
    lines = list(invoice.lines.all())
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

    invoice.gross_amount = totals.gross
    invoice.discount_amount = totals.discount
    invoice.taxable_amount = totals.taxable
    invoice.tax_amount = totals.tax
    invoice.rounding_amount = totals.rounding
    invoice.payable_amount = totals.payable
    invoice.save(
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
def issue_invoice(
    invoice: SalesInvoice,
    *,
    actor: Any = None,
    rounding_step: Decimal = DEFAULT_ROUNDING_STEP,
) -> IssuedInvoice:
    """Take the number, move the stock, fix the totals.

    All in one transaction, and the number is taken first so every stock movement carries it.
    If anything fails — not enough stock, an expired batch — the whole bill rolls back and the
    number is not consumed, which is what keeps the run gapless.
    """
    _require_editable(invoice)
    lines = list(invoice.lines.select_related("item", "unit", "item__tax_category").all())
    if not lines:
        raise DomainError(errors.INVOICE_HAS_NO_LINES)

    issued = issue_number(
        document_type=SALES_INVOICE, branch=invoice.branch, on_date=invoice.invoice_date
    )

    entries: list[StockLedgerEntry] = []
    for line in lines:
        allocations = allocate_fefo(
            item=line.item,
            branch=invoice.branch,
            quantity=line.base_quantity,
            on_date=invoice.invoice_date,
        )
        for allocation in allocations:
            unit_cost = allocation.batch.cost if allocation.batch else Decimal("0")
            SalesInvoiceLineBatch.objects.create(
                line=line,
                batch=allocation.batch,
                quantity=allocation.quantity,
                unit_cost=unit_cost,
            )
            entries.append(
                post_movement(
                    item=line.item,
                    branch=invoice.branch,
                    location=allocation.location,
                    batch=allocation.batch,
                    quantity=-allocation.quantity,
                    movement_type=MovementType.SALE,
                    unit_cost=unit_cost,
                    occurred_on=invoice.invoice_date,
                    actor=actor,
                    document_type=SALES_INVOICE,
                    document_id=str(invoice.pk),
                    document_number=issued.number,
                    document_line_id=str(line.pk),
                )
            )

    recalculate(invoice, rounding_step=rounding_step)
    invoice.number = issued.number
    invoice.fiscal_year = issued.fiscal_year
    invoice.status = InvoiceStatus.ISSUED
    invoice.issued_at = timezone.now()
    invoice.save(update_fields=["number", "fiscal_year", "status", "issued_at", "updated_at"])

    audit.record(
        action=AuditAction.CREATE,
        actor=actor,
        entity=invoice,
        entity_label=f"{issued.number} — {invoice.payable_amount}",
        changes={"status": {"from": InvoiceStatus.DRAFT, "to": InvoiceStatus.ISSUED}},
        branch=invoice.branch,
    )
    logger.info(
        "invoice_issued",
        number=issued.number,
        amount=str(invoice.payable_amount),
        lines=len(lines),
    )
    return IssuedInvoice(invoice=invoice, entries=entries)


def record_print(invoice: SalesInvoice) -> int:
    """Count a print, and say whether this one is a copy.

    Reprinting is not forbidden, but an unmarked second original is how one sale becomes two
    records. The count is kept so anything after the first can be marked as a copy.
    """
    SalesInvoice.objects.filter(pk=invoice.pk).update(print_count=F("print_count") + 1)
    invoice.refresh_from_db(fields=["print_count"])
    return invoice.print_count


def is_copy(invoice: SalesInvoice) -> bool:
    return invoice.print_count > 1


@transaction.atomic
def cancel_invoice(invoice: SalesInvoice, *, reason: str, actor: Any = None) -> SalesInvoice:
    """Cancel an issued invoice and put the stock back.

    The invoice keeps its number and its lines. IRD's rule is that a bill is never deleted, and a
    gap in the numbering is the first thing an inspection asks about.

    Note: IRD expects a cancellation to be evidenced by a credit note. That document does not
    exist yet — see the checklist. This reverses the stock and marks the invoice, which is correct
    but not yet sufficient for a tax audit.
    """
    if invoice.status == InvoiceStatus.CANCELLED:
        return invoice
    if invoice.status != InvoiceStatus.ISSUED:
        raise DomainError(errors.INVOICE_NOT_EDITABLE, "Only an issued invoice can be cancelled.")

    entries = StockLedgerEntry.objects.filter(
        document_type=SALES_INVOICE, document_id=str(invoice.pk)
    ).exclude(movement_type=MovementType.REVERSAL)
    for entry in entries:
        reverse_movement(entry, reason=reason, actor=actor)

    invoice.status = InvoiceStatus.CANCELLED
    invoice.cancelled_at = timezone.now()
    invoice.cancelled_reason = reason
    invoice.save(update_fields=["status", "cancelled_at", "cancelled_reason", "updated_at"])

    audit.record(
        action=AuditAction.VOID,
        actor=actor,
        entity=invoice,
        entity_label=invoice.number,
        changes={"status": {"from": InvoiceStatus.ISSUED, "to": InvoiceStatus.CANCELLED}},
        reason=reason,
        branch=invoice.branch,
    )
    return invoice


# --------------------------------------------------------------------------- traceability
def customers_who_received_batch(batch: Any) -> list[SalesInvoice]:
    """Who was sold stock from this batch. The question a recall asks."""
    invoice_ids = SalesInvoiceLineBatch.objects.filter(batch=batch).values_list(
        "line__invoice_id", flat=True
    )
    return list(
        SalesInvoice.objects.filter(pk__in=invoice_ids, status=InvoiceStatus.ISSUED).order_by(
            "-invoice_date"
        )
    )
