"""Whoever is on the other side of a document."""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.foundation.models import ArchivableModel
from kernel.tenancy.models import TenantScopedModel, pan_validator


class PartyKind(models.TextChoices):
    INDIVIDUAL = "individual", _("Individual")
    BUSINESS = "business", _("Business")
    HOSPITAL = "hospital", _("Hospital or clinic")
    GOVERNMENT = "government", _("Government body")


class Party(TenantScopedModel, ArchivableModel):
    """A supplier, a customer, or both.

    Roles are flags rather than separate tables: a distributor that also buys back expired stock
    is one relationship with one ledger, not two records that have to be kept in step.
    """

    kind = models.CharField(max_length=20, choices=PartyKind.choices, default=PartyKind.BUSINESS)
    is_supplier = models.BooleanField(default=False)
    is_customer = models.BooleanField(default=False)

    name = models.CharField(max_length=200)
    name_ne = models.CharField(max_length=200, blank=True)
    #: Required on a tax invoice above the IRD threshold, and on every purchase from a
    #: VAT-registered supplier.
    pan = models.CharField(_("PAN"), max_length=9, blank=True, validators=[pan_validator])
    is_vat_registered = models.BooleanField(default=False)

    phone = models.CharField(max_length=16, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=300, blank=True)

    #: A supplier's DDA licence. Selling restricted drugs to an unlicensed buyer is an offence,
    #: so the same field carries the buyer's licence when the party is a customer.
    dda_licence_number = models.CharField(max_length=50, blank=True)
    dda_licence_expiry = models.DateField(null=True, blank=True)

    credit_limit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        help_text=_("Zero means no credit is extended."),
    )
    credit_days = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name_plural = "parties"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="parties_unique_name"),
            models.CheckConstraint(
                condition=models.Q(is_supplier=True) | models.Q(is_customer=True),
                name="parties_must_be_supplier_or_customer",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "phone"])]

    def __str__(self) -> str:
        return self.name

    def has_valid_licence_on(self, on_date: object) -> bool:
        if not self.dda_licence_number:
            return False
        return self.dda_licence_expiry is None or self.dda_licence_expiry >= on_date  # type: ignore[operator]
