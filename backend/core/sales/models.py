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


class CreditNoteKind(models.TextChoices):
    """Why the credit note exists, which decides whether stock moves."""

    #: The whole invoice is being undone. The stock is reversed by the cancellation itself, so the
    #: credit note here is tax evidence rather than a stock document.
    CANCELLATION = "cancellation", _("Cancellation of an invoice")
    #: Goods have come back over the counter. This is the document that brings them back in.
    RETURN = "return", _("Goods returned by the customer")
    #: Money only — an overcharge, or a discount agreed afterwards. Nothing comes back.
    ADJUSTMENT = "adjustment", _("Price adjustment")


class ReturnReason(models.TextChoices):
    CUSTOMER_CHANGED_MIND = "changed_mind", _("Customer changed their mind")
    WRONG_ITEM = "wrong_item", _("Wrong item supplied")
    DAMAGED = "damaged", _("Damaged")
    EXPIRED = "expired", _("Expired or near expiry")
    ADVERSE_REACTION = "adverse_reaction", _("Adverse reaction")
    RATE_DIFFERENCE = "rate_difference", _("Rate difference")
    INVOICE_CANCELLED = "invoice_cancelled", _("Invoice cancelled")
    OTHER = "other", _("Other")


class ReturnDestination(models.TextChoices):
    """Where returned stock goes.

    Quarantine is the default, and for medicines it should stay the default. Once a pack has left
    the premises nobody can say how it was kept, and a tablet that spent a hot afternoon in a bag
    is not stock to sell to the next person. Putting it back on the shelf is a decision somebody
    makes deliberately, for a sealed pack that never really left the counter.
    """

    QUARANTINE = "quarantine", _("Quarantine, pending inspection")
    SELLABLE = "sellable", _("Back on the shelf")


class CreditNote(TenantScopedModel):
    """The document IRD requires when an invoice is reduced or undone.

    A sale is never deleted and an invoice is never edited, so the only lawful way to take money
    back off a bill is to issue a credit note against it. Numbered in its own series, per branch
    and per fiscal year, exactly like the invoice it credits.
    """

    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="credit_notes")
    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    #: Where returned goods are put. Unused by a cancellation or an adjustment.
    location = models.ForeignKey(
        "tenancy.Location", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    kind = models.CharField(max_length=20, choices=CreditNoteKind.choices)
    reason_code = models.CharField(
        max_length=20, choices=ReturnReason.choices, default=ReturnReason.OTHER
    )
    reason = models.CharField(max_length=300)
    destination = models.CharField(
        max_length=20, choices=ReturnDestination.choices, default=ReturnDestination.QUARANTINE
    )

    number = models.CharField(max_length=60, blank=True, help_text=_("Assigned when issued."))
    fiscal_year = models.CharField(max_length=9, blank=True)
    note_date = models.DateField()

    status = models.CharField(
        max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT, db_index=True
    )
    issued_at = models.DateTimeField(null=True, blank=True)

    #: Copied from the invoice, so the arithmetic runs the same way round as it did on the sale.
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
    rounding_amount = models.DecimalField(
        max_digits=8, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    #: What is owed back to the customer. Held positive, like an invoice: the direction is the
    #: document, not the sign, which is how it reads on a printed note and in a VAT return.
    payable_amount = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )

    print_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-note_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "branch", "number"],
                condition=~models.Q(number=""),
                name="sales_unique_credit_note_number_per_branch",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "branch", "-note_date"]),
            models.Index(fields=["tenant", "fiscal_year"]),
        ]

    def __str__(self) -> str:
        return self.number or "draft credit note"

    @property
    def is_editable(self) -> bool:
        return self.status == InvoiceStatus.DRAFT

    @property
    def moves_stock(self) -> bool:
        return self.kind == CreditNoteKind.RETURN


class CreditNoteLine(TenantScopedModel):
    """One returned or credited line, pointing at the invoice line it reduces.

    Pointing at the line rather than only at the item is what makes "you cannot return more than
    you bought" a question the database can answer.
    """

    credit_note = models.ForeignKey(CreditNote, on_delete=models.CASCADE, related_name="lines")
    invoice_line = models.ForeignKey(
        SalesInvoiceLine, on_delete=models.PROTECT, related_name="credit_note_lines"
    )
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey("catalog.UnitOfMeasure", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        "inventory.Batch", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    quantity = models.DecimalField(max_digits=18, decimal_places=QUANTITY_DECIMALS)
    base_quantity = models.DecimalField(
        max_digits=18, decimal_places=QUANTITY_DECIMALS, default=Decimal("0")
    )
    #: Copied from the invoice line. A credit note is priced at what was charged, never at today's
    #: price: crediting a customer at a rate they never paid turns a refund into a discount.
    rate = models.DecimalField(max_digits=18, decimal_places=MONEY_DECIMALS)
    discount_percent = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"))
    tax_percentage = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"))
    unit_cost = models.DecimalField(
        max_digits=18, decimal_places=MONEY_DECIMALS, default=Decimal("0")
    )

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
        ordering = ["credit_note", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="sales_credit_line_quantity_positive"
            )
        ]
        indexes = [models.Index(fields=["tenant", "batch"])]

    def __str__(self) -> str:
        return f"{self.quantity} of {self.item_id} returned"
