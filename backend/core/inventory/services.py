"""Moving stock, and choosing which batch moves."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

import structlog
from django.db import models, transaction
from django.utils import timezone

from core.catalog.services import quantize_quantity
from shared.errors import DomainError

from . import errors
from .models import (
    Batch,
    BatchStatus,
    MovementType,
    StockBalance,
    StockLedgerEntry,
)

logger = structlog.get_logger(__name__)

#: Movements that hand stock to a customer. Expiry is a hard stop for these and only these —
#: writing off or returning expired stock has to stay possible, or it could never leave the shelf.
SELLING_MOVEMENTS = frozenset({MovementType.SALE})


@dataclass(frozen=True, slots=True)
class Allocation:
    batch: Batch | None
    location: Any
    quantity: Decimal

    def __str__(self) -> str:
        return f"{self.quantity} from {self.batch or 'unbatched'}"


# --------------------------------------------------------------------------- choosing a batch
def allocate_fefo(
    *,
    item: Any,
    branch: Any,
    quantity: Decimal | int | str,
    on_date: date | None = None,
    location: Any = None,
) -> list[Allocation]:
    """Pick batches nearest to expiry first.

    First Expiry First Out, not First In First Out: what matters is what will go out of date
    soonest, which is not always what arrived first. This is the mechanism behind the promise of
    zero expired sales — the stock most at risk leaves the shelf first, on its own.
    """
    wanted = quantize_quantity(Decimal(str(quantity)))
    if wanted <= 0:
        raise ValueError("Allocate a quantity greater than zero.")
    on_date = on_date or timezone.localdate()

    balances = StockBalance.objects.filter(item=item, branch=branch, quantity__gt=0).select_related(
        "batch", "location"
    )
    if location is not None:
        balances = balances.filter(location=location)

    sellable = [
        balance
        for balance in balances
        if balance.batch is None or balance.batch.is_sellable_on(on_date)
    ]
    # Nearest expiry first; unbatched stock and stock with no expiry go last, since they carry
    # no risk of going out of date.
    sellable.sort(
        key=lambda balance: (
            balance.batch is None or balance.batch.expiry_date is None,
            balance.batch.expiry_date if balance.batch and balance.batch.expiry_date else date.max,
            str(balance.batch.number) if balance.batch else "",
        )
    )

    allocations: list[Allocation] = []
    remaining = wanted
    for balance in sellable:
        if remaining <= 0:
            break
        take = min(balance.quantity, remaining)
        allocations.append(
            Allocation(batch=balance.batch, location=balance.location, quantity=take)
        )
        remaining -= take

    if remaining > 0:
        available = wanted - remaining
        raise DomainError(
            errors.INSUFFICIENT_STOCK,
            f"{item.name}: {available} available, {wanted} needed.",
        )
    return allocations


def available_quantity(*, item: Any, branch: Any, on_date: date | None = None) -> Decimal:
    """What could actually be sold today — expired and quarantined stock does not count."""
    on_date = on_date or timezone.localdate()
    balances = StockBalance.objects.filter(item=item, branch=branch).select_related("batch")
    return quantize_quantity(
        sum(
            (
                balance.quantity
                for balance in balances
                if balance.batch is None or balance.batch.is_sellable_on(on_date)
            ),
            Decimal("0"),
        )
    )


def on_hand_quantity(*, item: Any, branch: Any) -> Decimal:
    """Everything physically present, saleable or not. This is what a stock count should find."""
    total = StockBalance.objects.filter(item=item, branch=branch).aggregate(
        total=models.Sum("quantity")
    )["total"]
    return quantize_quantity(total or Decimal("0"))


# --------------------------------------------------------------------------- moving stock
@transaction.atomic
def post_movement(
    *,
    item: Any,
    branch: Any,
    location: Any,
    quantity: Decimal | int | str,
    movement_type: str,
    batch: Batch | None = None,
    unit_cost: Decimal | int | str = Decimal("0"),
    occurred_on: date | None = None,
    actor: Any = None,
    document_type: str = "",
    document_id: str = "",
    document_number: str = "",
    document_line_id: str = "",
    note: str = "",
    allow_negative: bool = False,
    reverses: StockLedgerEntry | None = None,
) -> StockLedgerEntry:
    """Record one movement and update the balance it affects.

    The ledger entry and the balance change are one transaction, so the two can never disagree
    because something failed halfway.
    """
    moved = quantize_quantity(Decimal(str(quantity)))
    if moved == 0:
        raise ValueError("A movement of zero is not a movement.")
    occurred_on = occurred_on or timezone.localdate()

    if batch is not None and moved < 0 and movement_type in SELLING_MOVEMENTS:
        _refuse_unsellable(batch, occurred_on)

    balance = cast(
        "StockBalance",
        StockBalance.objects.select_for_update().get_or_create(
            branch=branch,
            location=location,
            item=item,
            batch=batch,
            defaults={"quantity": Decimal("0")},
        )[0],
    )
    new_quantity = quantize_quantity(balance.quantity + moved)
    if new_quantity < 0 and not allow_negative:
        raise DomainError(
            errors.INSUFFICIENT_STOCK,
            f"{item.name}: {balance.quantity} on hand, {abs(moved)} being taken out.",
        )

    entry = cast(
        "StockLedgerEntry",
        StockLedgerEntry.objects.create(
            branch=branch,
            location=location,
            item=item,
            batch=batch,
            movement_type=movement_type,
            quantity=moved,
            unit_cost=Decimal(str(unit_cost)),
            occurred_on=occurred_on,
            posted_by=actor,
            document_type=document_type,
            document_id=document_id,
            document_number=document_number,
            document_line_id=document_line_id,
            note=note,
            reverses=reverses,
        ),
    )

    balance.quantity = new_quantity
    balance.save(update_fields=["quantity", "updated_at"])
    return entry


def _refuse_unsellable(batch: Batch, on_date: date) -> None:
    if batch.is_expired_on(on_date):
        raise DomainError(
            errors.EXPIRED_BATCH,
            f"Batch {batch.number} expired on {batch.expiry_date}.",
        )
    if batch.status not in BatchStatus.sellable():
        raise DomainError(
            errors.BATCH_NOT_SELLABLE,
            f"Batch {batch.number} is {batch.get_status_display().lower()}.",
        )


@transaction.atomic
def receive_stock(
    *,
    item: Any,
    branch: Any,
    location: Any,
    quantity: Decimal | int | str,
    batch_number: str = "",
    expiry_date: date | None = None,
    manufactured_date: date | None = None,
    mrp: Decimal | None = None,
    unit_cost: Decimal | int | str = Decimal("0"),
    occurred_on: date | None = None,
    movement_type: str = MovementType.RECEIPT,
    actor: Any = None,
    **document: Any,
) -> tuple[StockLedgerEntry, Batch | None]:
    """Bring stock in, creating the batch if this is the first time it has been seen."""
    occurred_on = occurred_on or timezone.localdate()
    batch = None

    if item.is_batch_tracked:
        if not batch_number:
            raise ValueError(f"{item.name} is tracked by batch, so a batch number is required.")
        if item.is_expiry_tracked and expiry_date is None:
            raise ValueError(f"{item.name} is tracked by expiry, so an expiry date is required.")
        batch, _ = cast(
            "tuple[Batch, bool]",
            Batch.objects.get_or_create(
                item=item,
                number=batch_number,
                defaults={
                    "expiry_date": expiry_date,
                    "manufactured_date": manufactured_date,
                    "mrp": mrp,
                    "cost": Decimal(str(unit_cost)),
                    "received_on": occurred_on,
                },
            ),
        )

    entry = post_movement(
        item=item,
        branch=branch,
        location=location,
        batch=batch,
        quantity=abs(quantize_quantity(Decimal(str(quantity)))),
        movement_type=movement_type,
        unit_cost=unit_cost,
        occurred_on=occurred_on,
        actor=actor,
        **document,
    )
    return entry, batch


@transaction.atomic
def issue_stock(
    *,
    item: Any,
    branch: Any,
    quantity: Decimal | int | str,
    movement_type: str = MovementType.SALE,
    occurred_on: date | None = None,
    location: Any = None,
    actor: Any = None,
    **document: Any,
) -> list[StockLedgerEntry]:
    """Take stock out, spreading it across batches nearest to expiry first."""
    occurred_on = occurred_on or timezone.localdate()
    allocations = allocate_fefo(
        item=item, branch=branch, quantity=quantity, on_date=occurred_on, location=location
    )
    return [
        post_movement(
            item=item,
            branch=branch,
            location=allocation.location,
            batch=allocation.batch,
            quantity=-allocation.quantity,
            movement_type=movement_type,
            unit_cost=allocation.batch.cost if allocation.batch else Decimal("0"),
            occurred_on=occurred_on,
            actor=actor,
            **document,
        )
        for allocation in allocations
    ]


@transaction.atomic
def reverse_movement(
    entry: StockLedgerEntry, *, reason: str, actor: Any = None
) -> StockLedgerEntry:
    """Undo a movement by posting its opposite.

    The original stays exactly as it was. A stock ledger that can be edited proves nothing.
    """
    return post_movement(
        item=entry.item,
        branch=entry.branch,
        location=entry.location,
        batch=entry.batch,
        quantity=-entry.quantity,
        movement_type=MovementType.REVERSAL,
        unit_cost=entry.unit_cost,
        occurred_on=timezone.localdate(),
        actor=actor,
        document_type=entry.document_type,
        document_id=entry.document_id,
        document_number=entry.document_number,
        note=reason,
        reverses=entry,
        allow_negative=True,
    )


# --------------------------------------------------------------------------- expiry
def expire_batches(*, on_date: date | None = None) -> int:
    """Mark batches that have gone out of date. Run daily.

    Selling is already blocked by date, so this is about making the shelf state visible rather
    than about safety — an expired batch should look expired in a stock list, not merely behave
    that way at the counter.
    """
    on_date = on_date or timezone.localdate()
    stale = Batch.objects.filter(status=BatchStatus.AVAILABLE, expiry_date__lt=on_date)
    count = stale.update(status=BatchStatus.EXPIRED, status_reason=f"Expired on {on_date}")
    if count:
        logger.info("batches_expired", count=count, on_date=on_date.isoformat())
    return count


def batches_expiring_within(
    *, days: int, branch: Any = None, on_date: date | None = None
) -> list[Batch]:
    """Stock to act on before it becomes a loss: discount it, return it, or move it."""
    on_date = on_date or timezone.localdate()
    query = Batch.objects.filter(
        status=BatchStatus.AVAILABLE,
        expiry_date__gte=on_date,
        expiry_date__lte=on_date + timedelta(days=days),
    ).select_related("item")
    if branch is not None:
        in_stock = StockBalance.objects.filter(branch=branch, quantity__gt=0).values("batch_id")
        query = query.filter(pk__in=models.Subquery(in_stock))
    return list(query.order_by("expiry_date"))


# --------------------------------------------------------------------------- reconciliation
@dataclass(frozen=True, slots=True)
class Discrepancy:
    location_id: Any
    item_id: Any
    batch_id: Any
    balance: Decimal
    ledger: Decimal

    @property
    def difference(self) -> Decimal:
        return self.balance - self.ledger


def reconcile() -> list[Discrepancy]:
    """Check the running balances against the ledger they are derived from.

    Reports rather than repairs: a disagreement means something wrote stock outside the service
    layer, and quietly correcting the number would hide that.
    """
    ledger_totals = {
        (row["location_id"], row["item_id"], row["batch_id"]): quantize_quantity(row["total"])
        for row in StockLedgerEntry.objects.values("location_id", "item_id", "batch_id").annotate(
            total=models.Sum("quantity")
        )
    }

    discrepancies: list[Discrepancy] = []
    seen: set[tuple[Any, Any, Any]] = set()

    for balance in StockBalance.objects.all():
        key = (balance.location_id, balance.item_id, balance.batch_id)
        seen.add(key)
        expected = ledger_totals.get(key, Decimal("0"))
        if quantize_quantity(balance.quantity) != expected:
            discrepancies.append(Discrepancy(*key, balance=balance.quantity, ledger=expected))

    for key, total in ledger_totals.items():
        if key not in seen and total != 0:
            discrepancies.append(Discrepancy(*key, balance=Decimal("0"), ledger=total))

    if discrepancies:
        logger.error("stock_balance_discrepancies", count=len(discrepancies))
    return discrepancies
