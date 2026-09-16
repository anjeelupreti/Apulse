"""Batches, stock movements and the balance those movements add up to."""

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.tenancy.models import TenantScopedModel

QUANTITY_DECIMALS = 3
MONEY_DECIMALS = 4


class BatchStatus(models.TextChoices):
    AVAILABLE = "available", _("Available")
    QUARANTINED = "quarantined", _("Quarantined")
    EXPIRED = "expired", _("Expired")
    RECALLED = "recalled", _("Recalled")
    DAMAGED = "damaged", _("Damaged")

    @classmethod
    def sellable(cls) -> tuple[str, ...]:
        return (cls.AVAILABLE,)


class Batch(TenantScopedModel):
    """One manufactured lot of an item.

    Expiry, MRP and cost all belong here rather than on the item, because they differ between
    lots of the same medicine — two boxes of the same brand on the same shelf can carry different
    printed prices and different expiry dates.
    """

    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT, related_name="batches")
    number = models.CharField(max_length=60, help_text=_("As printed on the pack."))
    #: The last day the stock may be used. A pack marked "EXP 09/2026" is usable to 30 Sep 2026.
    expiry_date = models.DateField(null=True, blank=True)
    manufactured_date = models.DateField(null=True, blank=True)
    #: Maximum retail price printed on this lot. Varies between lots, so it lives here.
    mrp = models.DecimalField(max_digits=18, decimal_places=MONEY_DECIMALS, null=True, blank=True)
    cost = models.DecimalField(
        max_digits=18,
        decimal_places=MONEY_DECIMALS,
        default=Decimal("0"),
        help_text=_("Landed cost of one base unit."),
    )
    status = models.CharField(
        max_length=20, choices=BatchStatus.choices, default=BatchStatus.AVAILABLE, db_index=True
    )
    status_reason = models.CharField(max_length=300, blank=True)
    received_on = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "batches"
        ordering = ["expiry_date", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "item", "number"], name="inventory_unique_batch_per_item"
            ),
            models.CheckConstraint(
                condition=models.Q(cost__gte=0), name="inventory_batch_cost_not_negative"
            ),
        ]
        indexes = [models.Index(fields=["tenant", "item", "expiry_date"])]

    def __str__(self) -> str:
        return f"{self.number} exp {self.expiry_date or 'n/a'}"

    def is_expired_on(self, on_date: date) -> bool:
        """Expired the day *after* the printed date: a pack is usable up to and including it."""
        return self.expiry_date is not None and on_date > self.expiry_date

    def is_sellable_on(self, on_date: date) -> bool:
        return self.status in BatchStatus.sellable() and not self.is_expired_on(on_date)

    def days_until_expiry(self, from_date: date) -> int | None:
        if self.expiry_date is None:
            return None
        return (self.expiry_date - from_date).days


class MovementType(models.TextChoices):
    OPENING = "opening", _("Opening stock")
    RECEIPT = "receipt", _("Goods received")
    SALE = "sale", _("Sold")
    SALE_RETURN = "sale_return", _("Returned by customer")
    PURCHASE_RETURN = "purchase_return", _("Returned to supplier")
    TRANSFER_OUT = "transfer_out", _("Transferred out")
    TRANSFER_IN = "transfer_in", _("Transferred in")
    ADJUSTMENT = "adjustment", _("Adjustment")
    WRITE_OFF = "write_off", _("Written off")
    REVERSAL = "reversal", _("Reversal of an earlier entry")


class StockLedgerEntry(TenantScopedModel):
    """One movement of stock. Append-only: see migration 0002.

    A mistake is corrected by posting the opposite entry, never by editing or deleting this one.
    An inspector asking "where did these forty tablets go" must get the whole story, including
    the parts someone would rather not show.
    """

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    location = models.ForeignKey("tenancy.Location", on_delete=models.PROTECT, related_name="+")
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        Batch, on_delete=models.PROTECT, null=True, blank=True, related_name="movements"
    )

    movement_type = models.CharField(max_length=20, choices=MovementType.choices, db_index=True)
    #: Signed, in the item's base units. Positive brings stock in, negative takes it out.
    quantity = models.DecimalField(max_digits=18, decimal_places=QUANTITY_DECIMALS)
    unit_cost = models.DecimalField(
        max_digits=18, decimal_places=MONEY_DECIMALS, default=Decimal("0")
    )

    #: What caused this. Free-form because the documents live in modules that may not be installed.
    document_type = models.CharField(max_length=60, blank=True)
    document_id = models.CharField(max_length=64, blank=True)
    document_number = models.CharField(max_length=60, blank=True)
    document_line_id = models.CharField(max_length=64, blank=True)

    occurred_on = models.DateField(help_text=_("The business date, which may not be today."))
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    #: Set on a reversal, pointing at what it undoes.
    reverses = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by"
    )
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name_plural = "stock ledger entries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "item", "-created_at"]),
            models.Index(fields=["tenant", "branch", "item", "batch"]),
            models.Index(fields=["tenant", "document_type", "document_id"]),
            models.Index(fields=["tenant", "occurred_on"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(quantity=0), name="inventory_movement_is_not_zero"
            )
        ]

    def __str__(self) -> str:
        return f"{self.movement_type} {self.quantity} of {self.item_id}"

    @property
    def value(self) -> Decimal:
        return self.quantity * self.unit_cost


class StockBalance(TenantScopedModel):
    """What is on hand, per batch and location.

    A running total kept for speed. The ledger is the truth; this is reconciled against it, and
    `reconcile()` reports any disagreement rather than silently correcting it.
    """

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    location = models.ForeignKey("tenancy.Location", on_delete=models.PROTECT, related_name="+")
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT, related_name="balances")
    batch = models.ForeignKey(
        Batch, on_delete=models.PROTECT, null=True, blank=True, related_name="balances"
    )
    quantity = models.DecimalField(
        max_digits=18, decimal_places=QUANTITY_DECIMALS, default=Decimal("0")
    )

    class Meta:
        ordering = ["item", "batch"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "location", "item", "batch"],
                name="inventory_one_balance_per_batch_location",
                nulls_distinct=False,
            )
        ]
        indexes = [models.Index(fields=["tenant", "item", "branch"])]

    def __str__(self) -> str:
        return f"{self.quantity} of {self.item_id} at {self.location_id}"


class InsufficientStockError(RuntimeError):
    """There is not enough sellable stock to cover what was asked for."""


class ExpiredStockError(RuntimeError):
    """An expired batch was about to move as if it were saleable."""
