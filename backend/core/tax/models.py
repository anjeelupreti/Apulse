"""How a line of an invoice is taxed."""

from datetime import date
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.foundation.models import BaseModel


class TaxTreatment(models.TextChoices):
    STANDARD = "standard", _("Taxable at the standard rate")
    EXEMPT = "exempt", _("Exempt from VAT")
    ZERO_RATED = "zero_rated", _("Zero-rated")


class TaxCategory(BaseModel):
    """A way of being taxed, shared by every account.

    Not tenant data: what VAT applies to is set by law, not by a pharmacy. Tenants choose which
    category an item belongs to; they do not invent categories or rates.
    """

    code = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    name_ne = models.CharField(max_length=100, blank=True)
    treatment = models.CharField(max_length=20, choices=TaxTreatment.choices)
    description = models.CharField(max_length=300, blank=True)
    #: Shown next to the category wherever it is chosen, so nobody guesses.
    guidance = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "tax categories"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name

    def rate_on(self, on_date: date) -> Decimal:
        """The percentage in force on a date. Zero for exempt and zero-rated."""
        rate = (
            self.rates.filter(effective_from__lte=on_date)
            .filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=on_date))
            .order_by("-effective_from")
            .first()
        )
        return rate.percentage if rate else Decimal("0")


class TaxRate(BaseModel):
    """A percentage and the period it applied for.

    Rates change, and a credit note against a two-year-old invoice has to use the rate that
    invoice carried — so rates are dated rather than overwritten.
    """

    category = models.ForeignKey(TaxCategory, on_delete=models.CASCADE, related_name="rates")
    percentage = models.DecimalField(max_digits=6, decimal_places=3)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["category", "-effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "effective_from"], name="tax_one_rate_per_start_date"
            ),
            models.CheckConstraint(
                condition=models.Q(percentage__gte=0), name="tax_rate_is_not_negative"
            ),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True)
                | models.Q(effective_to__gte=models.F("effective_from")),
                name="tax_rate_period_is_not_backwards",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category.code} {self.percentage}% from {self.effective_from}"
