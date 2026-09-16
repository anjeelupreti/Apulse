"""The sales invoice, its lines, and which batch each line came out of."""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.tenancy.models import TenantScopedModel

MONEY_DECIMALS = 4
AMOUNT_DECIMALS = 2
QUANTITY_DECIMALS = 3


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    ISSUED = "issued", _("Issued")
    CANCELLED = "cancelled", _("Cancelled")


class SalesInvoice(TenantScopedModel):
    """What the customer is given, and what IRD inspects.

    Draft until issued. Issuing takes the number, moves the stock and fixes the totals; after
    that nothing on it changes, because the customer is holding a copy.
    """

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    location = models.ForeignKey(
        "tenancy.Location",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=_("The counter the sale was made from."),
    )
    #: Blank for a walk-in customer, which is most of them.
    customer = models.ForeignKey(
        "parties.Party",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_invoices",
    )
    #: Kept even without a customer record, for reminders and for a recall.
    customer_name = models.CharField(max_length=200, blank=True)
    customer_phone = models.CharField(max_length=16, blank=True)

    number = models.CharField(max_length=60, blank=True, help_text=_("Assigned when issued."))
    fiscal_year = models.CharField(max_length=9, blank=True)
    invoice_date = models.DateField()

    status = models.CharField(
        max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT, db_index=True
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_reason = models.CharField(max_length=300, blank=True)

    #: Nepali retail prices contain their tax. Wholesale to another business usually does not.
    prices_include_tax = models.BooleanField(default=True)

    gross_amount = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    discount_amount = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    taxable_amount = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    tax_amount = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    #: The difference between the arithmetic and the amount actually handed over.
    rounding_amount = models.DecimalField(
        max_digits=8, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    payable_amount = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )

    #: Every reprint is counted. IRD requires copies after the first to be marked as copies.
    print_count = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-invoice_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "branch", "number"],
                condition=~models.Q(number=""),
                name="sales_unique_invoice_number_per_branch",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "branch", "-invoice_date"]),
            models.Index(fields=["tenant", "customer_phone"]),
            models.Index(fields=["tenant", "fiscal_year"]),
        ]

    def __str__(self) -> str:
        return self.number or "draft invoice"

    @property
    def is_editable(self) -> bool:
        return self.status == InvoiceStatus.DRAFT


class SalesInvoiceLine(TenantScopedModel):
    """One item on the bill, priced in the pack the customer is buying."""

    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey("catalog.UnitOfMeasure", on_delete=models.PROTECT, related_name="+")

    quantity = models.DecimalField(max_digits=18, decimal_places=QUANTITY_DECIMALS)
    #: In base units, worked out when the line is added, so stock and pricing never disagree.
    base_quantity = models.DecimalField(
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

    #: Copied from the tax category at the time. A rate change later must not alter an old bill.
    tax_percentage = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"))
    gross_amount = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    discount_amount = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    taxable_amount = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    tax_amount = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )

    class Meta:
        ordering = ["invoice", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="sales_line_quantity_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(rate__gte=0), name="sales_line_rate_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} of {self.item_id}"

    @property
    def total_amount(self) -> Decimal:
        return self.taxable_amount + self.tax_amount


class SalesInvoiceLineBatch(TenantScopedModel):
    """Which batch a line actually came out of, and how much of it.

    One line can draw on several batches when the first runs out. Recorded because a recall asks
    "who has this batch", and the honest answer has to come from somewhere.
    """

    line = models.ForeignKey(SalesInvoiceLine, on_delete=models.CASCADE, related_name="allocations")
    batch = models.ForeignKey(
        "inventory.Batch", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=QUANTITY_DECIMALS)
    #: What this stock cost, captured at the time so margin survives a later cost change.
    unit_cost = models.DecimalField(
        max_digits=18, decimal_places=MONEY_DECIMALS, default=Decimal("0")
    )

    class Meta:
        ordering = ["line", "created_at"]
        indexes = [models.Index(fields=["tenant", "batch"])]

    def __str__(self) -> str:
        return f"{self.quantity} from {self.batch_id or 'unbatched'}"
