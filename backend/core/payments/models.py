"""Money arriving and leaving, and the shift that has to account for it.

Two things live here and they answer different questions. A **payment** says how a particular bill
was settled. A **shift** says what the person on the till is answerable for between opening it and
counting it out.

Payments are append-only in the database. A payment taken in error is corrected by a reversing
payment, never by editing the original, for the same reason the stock ledger works that way: the
record of money changing hands is evidence, and evidence that can be rewritten proves nothing.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.tenancy.models import TenantScopedModel

AMOUNT_DECIMALS = 2


class PaymentModeKind(models.TextChoices):
    """How the money actually moves, which is what decides how it is counted and reconciled."""

    CASH = "cash", _("Cash")
    CARD = "card", _("Card")
    WALLET = "wallet", _("Digital wallet")
    QR = "qr", _("QR")
    BANK_TRANSFER = "bank_transfer", _("Bank transfer")
    CHEQUE = "cheque", _("Cheque")
    CREDIT = "credit", _("On account")


class PaymentMode(TenantScopedModel):
    """A way of paying that this pharmacy accepts.

    Per tenant rather than a fixed list: a shop in Kathmandu takes Fonepay and one in a district
    town may take nothing but cash, and neither should have to look at the other's buttons.

    `kind` is what the code reasons about — only `CASH` is counted in the drawer, only `CREDIT`
    leaves a balance owing — while the name is whatever the counter calls it.
    """

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=60)
    name_ne = models.CharField(max_length=60, blank=True)
    kind = models.CharField(max_length=20, choices=PaymentModeKind.choices)

    #: A wallet or a card terminal needs the transaction id kept; cash does not.
    requires_reference = models.BooleanField(default=False)
    #: Only cash can give change. Handing change out of a card payment is a way to empty a till.
    gives_change = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="payments_unique_mode_code_per_tenant"
            )
        ]

    def __str__(self) -> str:
        return self.name


class PaymentDirection(models.TextChoices):
    IN = "in", _("Received")
    OUT = "out", _("Paid out")


class Payment(TenantScopedModel):
    """One movement of money. Append-only: see migration 0002.

    Held against the document it settles, so "what is still owed on this bill" is a question with
    an answer rather than an opinion. A refund against a credit note is the same record pointing
    the other way.
    """

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    shift = models.ForeignKey(
        "payments.CashierShift",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments",
    )
    mode = models.ForeignKey(PaymentMode, on_delete=models.PROTECT, related_name="+")
    direction = models.CharField(max_length=3, choices=PaymentDirection.choices, db_index=True)

    #: Always positive. Which way it moved is `direction`, so a sign error cannot turn a refund
    #: into a receipt.
    amount = models.DecimalField(max_digits=18, decimal_places=AMOUNT_DECIMALS)
    #: What the customer actually handed over, when that is more than the bill. Cash only.
    tendered_amount = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    change_amount = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )

    #: Free-form because the documents live in modules that may not be installed — the same
    #: arrangement the stock ledger uses.
    document_type = models.CharField(max_length=60, blank=True)
    document_id = models.CharField(max_length=64, blank=True)
    document_number = models.CharField(max_length=60, blank=True)
    party = models.ForeignKey(
        "parties.Party", on_delete=models.PROTECT, null=True, blank=True, related_name="payments"
    )

    #: A wallet transaction id, a cheque number, a bank reference.
    reference = models.CharField(max_length=120, blank=True)
    received_on = models.DateField(help_text=_("The business date, which may not be today."))
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reverses = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by"
    )
    reason = models.CharField(max_length=300, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-received_on", "-created_at"]
        indexes = [
            models.Index(fields=["tenant", "document_type", "document_id"]),
            models.Index(fields=["tenant", "branch", "-received_on"]),
            models.Index(fields=["tenant", "shift"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="payments_amount_is_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(change_amount__gte=0), name="payments_change_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_direction_display()} {self.amount}"

    @property
    def signed_amount(self) -> Decimal:
        return self.amount if self.direction == PaymentDirection.IN else -self.amount


class ShiftStatus(models.TextChoices):
    OPEN = "open", _("Open")
    CLOSED = "closed", _("Closed")


class CashierShift(TenantScopedModel):
    """One person's turn on one till, from opening float to counted close.

    The unit of accountability. Without it, a shortfall found at the end of the day belongs to
    everybody who touched the drawer, which in practice means nobody.
    """

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="shifts")
    location = models.ForeignKey(
        "tenancy.Location",
        on_delete=models.PROTECT,
        related_name="shifts",
        help_text=_("The counter this till sits on."),
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shifts"
    )

    status = models.CharField(
        max_length=10, choices=ShiftStatus.choices, default=ShiftStatus.OPEN, db_index=True
    )
    business_date = models.DateField(help_text=_("The day this shift is counted against."))
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    #: The float put in at the start, so the first customer can be given change.
    opening_float = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    #: What the register says should be in the drawer. Written at close.
    expected_cash = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    #: What was actually counted, from the denomination sheet.
    counted_cash = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    #: Counted minus expected. Negative is short. Recorded, never quietly corrected.
    variance = models.DecimalField(
        max_digits=18, decimal_places=AMOUNT_DECIMALS, default=Decimal("0")
    )
    variance_reason = models.CharField(max_length=300, blank=True)

    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    #: A supervisor's sign-off. A cashier counting their own drawer alone is not a control.
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-business_date", "-opened_at"]
        constraints = [
            #: One open shift per till. Two people on one drawer means neither of them can
            #: be asked about a shortfall.
            models.UniqueConstraint(
                fields=["tenant", "location"],
                condition=models.Q(status="open"),
                name="payments_one_open_shift_per_location",
            )
        ]
        indexes = [models.Index(fields=["tenant", "branch", "-business_date"])]

    def __str__(self) -> str:
        return f"{self.cashier_id} at {self.location_id} on {self.business_date}"

    @property
    def is_open(self) -> bool:
        return self.status == ShiftStatus.OPEN

    @property
    def is_short(self) -> bool:
        return self.variance < 0


class CashMovementKind(models.TextChoices):
    FLOAT_IN = "float_in", _("Float added")
    PETTY_EXPENSE = "petty_expense", _("Petty expense")
    BANKED = "banked", _("Taken to the bank")
    DROP = "drop", _("Moved to the safe")
    CORRECTION = "correction", _("Correction")


class CashMovement(TenantScopedModel):
    """Cash into or out of the drawer for a reason that is not a sale. Append-only.

    The bus fare paid out of the till, the float topped up mid-afternoon, the bundle taken to the
    bank. Every one of them has to be written down or the count at the end of the shift is a
    number with no story behind it.
    """

    shift = models.ForeignKey(CashierShift, on_delete=models.PROTECT, related_name="cash_movements")
    kind = models.CharField(max_length=20, choices=CashMovementKind.choices)
    #: Signed: positive into the drawer, negative out of it.
    amount = models.DecimalField(max_digits=18, decimal_places=AMOUNT_DECIMALS)
    reason = models.CharField(max_length=300)
    reference = models.CharField(max_length=120, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    #: Required for anything leaving the drawer. One person alone with the till is not a control.
    witness_name = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(amount=0), name="payments_cash_movement_is_not_zero"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.amount}"


class DenominationCount(TenantScopedModel):
    """How many of each note and coin were counted at the close.

    Kept rather than just the total, because "twelve five-hundreds" is checkable against the
    drawer and "6,000" is not, and because a shortfall usually shows up as one denomination
    being wrong rather than a round number going missing.
    """

    shift = models.ForeignKey(CashierShift, on_delete=models.CASCADE, related_name="denominations")
    #: Face value in rupees: 1000, 500, 100, 50, 20, 10, 5, 2, 1.
    value = models.PositiveIntegerField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-value"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "shift", "value"],
                name="payments_one_count_per_denomination",
            )
        ]

    def __str__(self) -> str:
        return f"{self.count} x {self.value}"

    @property
    def total(self) -> Decimal:
        return Decimal(self.value) * self.count
