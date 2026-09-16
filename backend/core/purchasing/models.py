"""The goods received note and its lines."""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.tenancy.models import TenantScopedModel

MONEY_DECIMALS = 4
QUANTITY_DECIMALS = 3


class ReceiptStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    POSTED = "posted", _("Posted")
    CANCELLED = "cancelled", _("Cancelled")


class GoodsReceipt(TenantScopedModel):
    """One delivery from one supplier, against one supplier invoice.

    Draft until posted. Posting is what creates batches and moves stock, so a half-entered
    delivery never affects what the counter can sell.
    """

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    location = models.ForeignKey(
        "tenancy.Location",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=_("Where the delivery is put away."),
    )
    supplier = models.ForeignKey(
        "parties.Party", on_delete=models.PROTECT, related_name="goods_receipts"
    )

    number = models.CharField(max_length=60, blank=True, help_text=_("Assigned when posted."))
    #: The supplier's own invoice. Their number, not ours.
    supplier_invoice_number = models.CharField(max_length=60)
    supplier_invoice_date = models.DateField()
    received_on = models.DateField()

    status = models.CharField(
        max_length=20, choices=ReceiptStatus.choices, default=ReceiptStatus.DRAFT, db_index=True
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_reason = models.CharField(max_length=300, blank=True)

    #: Charges that arrive on the invoice but belong to the stock, spread across the lines.
    freight_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-received_on", "-created_at"]
        constraints = [
            # The same supplier invoice entered twice is the most common way stock is doubled.
            models.UniqueConstraint(
                fields=["tenant", "supplier", "supplier_invoice_number"],
                name="purchasing_one_receipt_per_supplier_invoice",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "branch", "-received_on"]),
            models.Index(fields=["tenant", "supplier", "-received_on"]),
        ]

    def __str__(self) -> str:
        return self.number or f"draft against {self.supplier_invoice_number}"

    @property
    def is_editable(self) -> bool:
        return self.status == ReceiptStatus.DRAFT


class GoodsReceiptLine(TenantScopedModel):
    """One item on a delivery, in the pack it was bought in."""

    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(
        "catalog.UnitOfMeasure",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=_("The pack this was bought in, such as a box of 100."),
    )

    quantity = models.DecimalField(max_digits=18, decimal_places=QUANTITY_DECIMALS)
    #: "10 + 1 free" — charged for none of it, but it is stock and it lowers the unit cost.
    free_quantity = models.DecimalField(
        max_digits=18, decimal_places=QUANTITY_DECIMALS, default=Decimal("0")
    )
    rate = models.DecimalField(
        max_digits=18, decimal_places=MONEY_DECIMALS, help_text=_("Price of one pack.")
    )
    discount_percent = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )

    batch_number = models.CharField(max_length=60, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    manufactured_date = models.DateField(null=True, blank=True)
    #: Printed on this lot. Differs between lots of the same medicine.
    mrp = models.DecimalField(max_digits=18, decimal_places=MONEY_DECIMALS, null=True, blank=True)

    class Meta:
        ordering = ["receipt", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="purchasing_line_quantity_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(free_quantity__gte=0), name="purchasing_free_not_negative"
            ),
            models.CheckConstraint(
                condition=models.Q(rate__gte=0), name="purchasing_rate_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} {self.unit_id} of {self.item_id}"

    @property
    def gross_amount(self) -> Decimal:
        return self.quantity * self.rate

    @property
    def discount_amount(self) -> Decimal:
        return self.gross_amount * self.discount_percent / 100

    @property
    def net_amount(self) -> Decimal:
        """What the supplier charges for this line, before tax."""
        return self.gross_amount - self.discount_amount


class ReceiptNotEditableError(RuntimeError):
    """A posted or cancelled receipt was about to be changed."""
