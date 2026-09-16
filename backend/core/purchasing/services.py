"""Entering a delivery and posting it into stock."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

import structlog
from django.db import transaction
from django.utils import timezone

from core.catalog.models import Item, ItemUnit, UnitOfMeasure
from core.catalog.services import to_base
from core.inventory.models import MovementType, StockLedgerEntry
from core.inventory.services import receive_stock, reverse_movement
from core.tax.services import tax_on
from kernel.audit import services as audit
from kernel.audit import tracking
from kernel.audit.models import AuditAction
from kernel.numbering.services import issue_number
from shared.errors import DomainError

from . import errors
from .costing import LineCosting, allocate_freight, cost_line, quantize_cost
from .document_types import GOODS_RECEIPT
from .extensions import run_cancelled_hooks, run_posted_hooks
from .models import GoodsReceipt, GoodsReceiptLine, ReceiptStatus

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PostedReceipt:
    receipt: GoodsReceipt
    entries: list[StockLedgerEntry]
    costings: dict[Any, LineCosting]


# --------------------------------------------------------------------------- drafting
@transaction.atomic
def start_receipt(
    *,
    branch: Any,
    location: Any,
    supplier: Any,
    supplier_invoice_number: str,
    supplier_invoice_date: date,
    received_on: date | None = None,
    freight_amount: Decimal = Decimal("0"),
    note: str = "",
) -> GoodsReceipt:
    """Open a draft against a supplier's invoice."""
    if GoodsReceipt.objects.filter(
        supplier=supplier, supplier_invoice_number=supplier_invoice_number
    ).exists():
        raise DomainError(
            errors.SUPPLIER_INVOICE_ALREADY_ENTERED,
            f"Invoice {supplier_invoice_number} from {supplier.name} is already entered.",
        )

    return cast(
        "GoodsReceipt",
        GoodsReceipt.objects.create(
            branch=branch,
            location=location,
            supplier=supplier,
            supplier_invoice_number=supplier_invoice_number,
            supplier_invoice_date=supplier_invoice_date,
            received_on=received_on or timezone.localdate(),
            freight_amount=freight_amount,
            note=note,
        ),
    )


@transaction.atomic
def add_line(
    receipt: GoodsReceipt,
    *,
    item: Item,
    quantity: Decimal | int | str,
    rate: Decimal | int | str,
    unit: UnitOfMeasure | None = None,
    free_quantity: Decimal | int | str = Decimal("0"),
    discount_percent: Decimal | int | str = Decimal("0"),
    batch_number: str = "",
    expiry_date: date | None = None,
    manufactured_date: date | None = None,
    mrp: Decimal | None = None,
) -> GoodsReceiptLine:
    _require_editable(receipt)

    if unit is None:
        default = ItemUnit.objects.filter(item=item, is_purchase_default=True).first()
        unit = default.unit if default else item.base_unit

    return cast(
        "GoodsReceiptLine",
        GoodsReceiptLine.objects.create(
            receipt=receipt,
            item=item,
            unit=unit,
            quantity=Decimal(str(quantity)),
            free_quantity=Decimal(str(free_quantity)),
            rate=Decimal(str(rate)),
            discount_percent=Decimal(str(discount_percent)),
            batch_number=batch_number,
            expiry_date=expiry_date,
            manufactured_date=manufactured_date,
            mrp=Decimal(str(mrp)) if mrp is not None else None,
        ),
    )


def _require_editable(receipt: GoodsReceipt) -> None:
    if not receipt.is_editable:
        raise DomainError(errors.RECEIPT_NOT_EDITABLE)


# --------------------------------------------------------------------------- posting
@transaction.atomic
def post_receipt(
    receipt: GoodsReceipt,
    *,
    actor: Any = None,
    allow_expired: bool = False,
) -> PostedReceipt:
    """Turn a draft into stock: create the batches, move the stock, number the document.

    Everything happens in one transaction. A delivery that is half in stock is worse than one
    that is not in stock at all, because nobody knows which half.
    """
    _require_editable(receipt)
    lines = list(receipt.lines.select_related("item", "unit", "item__tax_category").all())
    if not lines:
        raise DomainError(errors.RECEIPT_HAS_NO_LINES)

    for line in lines:
        _validate_line(line, receipt=receipt, allow_expired=allow_expired)

    # Input VAT is recoverable for a registered business, so it is not part of the cost of stock.
    vat_is_recoverable = receipt.branch.legal_entity.is_vat_registered
    freight_shares = allocate_freight(receipt.freight_amount, [line.net_amount for line in lines])

    # Numbered before the movements, so each ledger entry carries the document number from the
    # start. The ledger is append-only, so there is no going back to fill it in afterwards — and
    # if anything below fails, the whole transaction rolls back and the number is not consumed.
    issued = issue_number(
        document_type=GOODS_RECEIPT, branch=receipt.branch, on_date=receipt.received_on
    )

    entries: list[StockLedgerEntry] = []
    costings: dict[Any, LineCosting] = {}

    for line, freight_share in zip(lines, freight_shares, strict=True):
        costing = _cost(line, freight_share=freight_share, vat_is_recoverable=vat_is_recoverable)
        costings[line.pk] = costing

        entry, _batch = receive_stock(
            item=line.item,
            branch=receipt.branch,
            location=receipt.location,
            quantity=costing.total_base_quantity,
            batch_number=line.batch_number,
            expiry_date=line.expiry_date,
            manufactured_date=line.manufactured_date,
            mrp=_mrp_per_base_unit(line),
            unit_cost=costing.unit_cost,
            occurred_on=receipt.received_on,
            movement_type=MovementType.RECEIPT,
            actor=actor,
            document_type=GOODS_RECEIPT,
            document_id=str(receipt.pk),
            document_number=issued.number,
            document_line_id=str(line.pk),
        )
        entries.append(entry)

    with tracking.paused():
        receipt.number = issued.number
        receipt.status = ReceiptStatus.POSTED
        receipt.posted_at = timezone.now()
        receipt.save(update_fields=["number", "status", "posted_at", "updated_at"])

    audit.record(
        action=AuditAction.CREATE,
        actor=actor,
        entity=receipt,
        entity_label=f"{issued.number} from {receipt.supplier.name}",
        changes={"status": {"from": ReceiptStatus.DRAFT, "to": ReceiptStatus.POSTED}},
        branch=receipt.branch,
    )
    # The pharmacy module writes the narcotic register here. A register that only records what
    # left the cabinet cannot be reconciled against what is in it.
    run_posted_hooks(receipt, entries=entries, actor=actor)

    logger.info(
        "goods_receipt_posted",
        number=issued.number,
        supplier=receipt.supplier.name,
        lines=len(lines),
    )
    return PostedReceipt(receipt=receipt, entries=entries, costings=costings)


def _validate_line(line: GoodsReceiptLine, *, receipt: GoodsReceipt, allow_expired: bool) -> None:
    if line.item.is_batch_tracked and not line.batch_number:
        raise DomainError(errors.BATCH_DETAILS_REQUIRED, f"{line.item.name} needs a batch number.")
    if line.item.is_expiry_tracked and line.expiry_date is None:
        raise DomainError(errors.BATCH_DETAILS_REQUIRED, f"{line.item.name} needs an expiry date.")
    if (
        not allow_expired
        and line.expiry_date is not None
        and line.expiry_date < receipt.received_on
    ):
        raise DomainError(
            errors.RECEIVING_EXPIRED_STOCK,
            f"{line.item.name} batch {line.batch_number} expired on {line.expiry_date}.",
        )


def _cost(
    line: GoodsReceiptLine, *, freight_share: Decimal, vat_is_recoverable: bool
) -> LineCosting:
    charged = to_base(line.item, line.quantity, line.unit)
    free = to_base(line.item, line.free_quantity, line.unit) if line.free_quantity else Decimal("0")
    tax = tax_on(line.net_amount, line.item.tax_category, on_date=line.receipt.received_on)
    return cost_line(
        charged_base_quantity=charged,
        free_base_quantity=free,
        net_amount=line.net_amount,
        freight_share=freight_share,
        tax_amount=tax.tax,
        vat_is_recoverable=vat_is_recoverable,
    )


def _mrp_per_base_unit(line: GoodsReceiptLine) -> Decimal | None:
    """MRP is printed on the pack; stock is costed per base unit, so convert."""
    if line.mrp is None:
        return None
    pack = ItemUnit.objects.filter(item=line.item, unit=line.unit).first()
    factor = pack.factor if pack else Decimal("1")
    return quantize_cost(line.mrp / factor)


# --------------------------------------------------------------------------- cancelling
@transaction.atomic
def cancel_receipt(receipt: GoodsReceipt, *, reason: str, actor: Any = None) -> GoodsReceipt:
    """Undo a posted receipt by reversing every movement it made.

    The receipt keeps its number and its lines. A cancelled document that disappears is a gap in
    the numbering, and a gap is what an inspection asks about.
    """
    if receipt.status == ReceiptStatus.CANCELLED:
        return receipt
    if receipt.status != ReceiptStatus.POSTED:
        raise DomainError(errors.RECEIPT_NOT_EDITABLE, "Only a posted receipt can be cancelled.")

    original = StockLedgerEntry.objects.filter(
        document_type=GOODS_RECEIPT, document_id=str(receipt.pk)
    ).exclude(movement_type=MovementType.REVERSAL)
    reversals = [reverse_movement(entry, reason=reason, actor=actor) for entry in original]

    with tracking.paused():
        receipt.status = ReceiptStatus.CANCELLED
        receipt.cancelled_at = timezone.now()
        receipt.cancelled_reason = reason
        receipt.save(update_fields=["status", "cancelled_at", "cancelled_reason", "updated_at"])

    audit.record(
        action=AuditAction.VOID,
        actor=actor,
        entity=receipt,
        entity_label=receipt.number,
        changes={"status": {"from": ReceiptStatus.POSTED, "to": ReceiptStatus.CANCELLED}},
        reason=reason,
        branch=receipt.branch,
    )

    run_cancelled_hooks(receipt, reason=reason, actor=actor, entries=reversals)
    return receipt
