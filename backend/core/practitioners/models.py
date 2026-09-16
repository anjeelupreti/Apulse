"""Whoever wrote the prescription."""

from datetime import date

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from kernel.foundation.models import ArchivableModel
from kernel.tenancy.models import TenantScopedModel


class Council(models.TextChoices):
    """The register a prescriber belongs to. Exact mapping per profession: CR-NMC-01."""

    MEDICAL = "nmc", _("Nepal Medical Council")
    DENTAL = "ndc", _("Nepal Dental Council")
    HEALTH_PROFESSIONAL = "nhpc", _("Nepal Health Professional Council")
    AYURVEDIC = "nayc", _("Nepal Ayurvedic Medical Council")
    OTHER = "other", _("Other")


class Practitioner(TenantScopedModel, ArchivableModel):
    """A prescriber a pharmacy dispenses against.

    Added at the counter as often as not, from whatever is legible on the prescription, so the
    registration number is optional and verification is a separate, later step. Refusing to record
    a prescriber because the number was unreadable would just mean the sale goes unrecorded.
    """

    name = models.CharField(max_length=200)
    name_ne = models.CharField(max_length=200, blank=True)
    council = models.CharField(max_length=10, choices=Council.choices, default=Council.MEDICAL)
    registration_number = models.CharField(max_length=50, blank=True)
    speciality = models.CharField(max_length=120, blank=True)
    workplace = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=16, blank=True)

    #: Checked against the council register by someone, at some point. Until then the prescriber
    #: is usable but marked unverified, which is the honest state for a name read off a pad.
    verified_on = models.DateField(null=True, blank=True)
    verified_note = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "council", "registration_number"],
                condition=~models.Q(registration_number=""),
                name="practitioners_unique_registration",
            )
        ]
        indexes = [models.Index(fields=["tenant", "name"])]

    def __str__(self) -> str:
        if self.registration_number:
            return f"{self.name} ({self.registration_number})"
        return self.name

    @property
    def is_verified(self) -> bool:
        return self.verified_on is not None

    def verify(self, *, on_date: date | None = None, note: str = "") -> None:
        self.verified_on = on_date or timezone.localdate()
        self.verified_note = note
        self.save(update_fields=["verified_on", "verified_note", "updated_at"])
