"""Medicines, the rules that govern them, and the prescriptions they are dispensed against."""

from datetime import date, timedelta

from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.foundation.models import BaseModel
from kernel.tenancy.models import TenantScopedModel


class DrugSchedule(models.TextChoices):
    """The समूह a medicine belongs to, which decides how it may be supplied."""

    KA = "ka", _("Samuha Ka (समूह क)")
    KHA = "kha", _("Samuha Kha (समूह ख)")
    GA = "ga", _("Samuha Ga (समूह ग)")
    #: Everything starts here. A medicine with no schedule is treated as the most restricted,
    #: because guessing the other way means handing over a controlled drug by mistake.
    UNCLASSIFIED = "unclassified", _("Not yet classified")


class DosageForm(models.TextChoices):
    TABLET = "tablet", _("Tablet")
    CAPSULE = "capsule", _("Capsule")
    SYRUP = "syrup", _("Syrup")
    SUSPENSION = "suspension", _("Suspension")
    INJECTION = "injection", _("Injection")
    OINTMENT = "ointment", _("Ointment or cream")
    DROPS = "drops", _("Drops")
    INHALER = "inhaler", _("Inhaler")
    POWDER = "powder", _("Powder")
    OTHER = "other", _("Other")


class ScheduleRule(BaseModel):
    """What a schedule requires, and when that was true.

    Platform data, not a pharmacy's to edit: these rules come from DDA. Dated, because a notice
    that moves a drug or changes a requirement must not rewrite how last year's sales were judged.

    Seeded from what the research found (CR-DDA-01). The official group lists are still needed
    before this can be relied on in a real pharmacy.
    """

    schedule = models.CharField(max_length=20, choices=DrugSchedule.choices)
    requires_prescription = models.BooleanField(default=False)
    requires_prescriber_registration = models.BooleanField(
        default=False, help_text=_("The prescriber's council registration must be recorded.")
    )
    requires_register_entry = models.BooleanField(
        default=False, help_text=_("A separate statutory register entry, as for narcotics.")
    )
    requires_pharmacist = models.BooleanField(
        default=False, help_text=_("A registered pharmacist must dispense it personally.")
    )
    #: Beyond this, a single dispensing needs a fresh prescription. Zero means no limit.
    max_days_supply = models.PositiveSmallIntegerField(default=0)

    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    source_note = models.CharField(
        max_length=300, blank=True, help_text=_("Which notice or Act this comes from.")
    )

    class Meta:
        ordering = ["schedule", "-effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "effective_from"], name="pharmacy_one_rule_per_start_date"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_schedule_display()} from {self.effective_from}"


class MedicineProfile(TenantScopedModel):
    """What makes an item a medicine.

    Separate from the item rather than fields on it, so a bandage, a bottle of shampoo and a
    thermometer are not carrying empty columns for strength and drug schedule.
    """

    item = models.OneToOneField("catalog.Item", on_delete=models.CASCADE, related_name="medicine")
    #: The international non-proprietary name — paracetamol, not Calpol. What substitution and
    #: interaction checks work from.
    generic_name = models.CharField(max_length=200)
    brand_name = models.CharField(max_length=200, blank=True)
    strength = models.CharField(max_length=60, blank=True, help_text=_("Such as 500mg."))
    dosage_form = models.CharField(
        max_length=20, choices=DosageForm.choices, default=DosageForm.TABLET
    )
    route = models.CharField(max_length=60, blank=True)

    schedule = models.CharField(
        max_length=20,
        choices=DrugSchedule.choices,
        default=DrugSchedule.UNCLASSIFIED,
        db_index=True,
    )
    #: The number under which DDA registered this product.
    dda_registration_number = models.CharField(max_length=60, blank=True)
    marketing_authorisation_holder = models.CharField(max_length=200, blank=True)

    requires_cold_chain = models.BooleanField(default=False)
    is_narcotic = models.BooleanField(
        default=False, help_text=_("Held in a locked cabinet and entered in the narcotic register.")
    )
    storage_note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["generic_name"]
        indexes = [
            models.Index(fields=["tenant", "generic_name"]),
            models.Index(fields=["tenant", "schedule"]),
        ]

    def __str__(self) -> str:
        parts = [self.generic_name]
        if self.strength:
            parts.append(self.strength)
        return " ".join(parts)


class Prescription(TenantScopedModel):
    """A prescription presented at the counter.

    Attached to the sale it justifies. The image matters as much as the fields: DDA's requirement
    for narcotics is that the doctor's prescription is kept *with* the record, not summarised into
    it.
    """

    invoice = models.ForeignKey(
        "sales.SalesInvoice",
        on_delete=models.CASCADE,
        related_name="prescriptions",
        null=True,
        blank=True,
    )
    prescriber = models.ForeignKey(
        "practitioners.Practitioner", on_delete=models.PROTECT, related_name="prescriptions"
    )
    patient = models.ForeignKey(
        "parties.Party",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="prescriptions",
    )
    #: Kept even without a customer record — most counter sales have no account.
    patient_name = models.CharField(max_length=200)
    patient_age = models.CharField(max_length=20, blank=True)
    patient_phone = models.CharField(max_length=16, blank=True)

    prescribed_on = models.DateField()
    valid_until = models.DateField(
        null=True, blank=True, help_text=_("After this a fresh prescription is needed.")
    )
    diagnosis = models.CharField(max_length=300, blank=True)

    #: Where the scan or photograph lives. Becomes a proper file reference with M2.7.
    attachment_reference = models.CharField(max_length=300, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-prescribed_on"]
        indexes = [
            models.Index(fields=["tenant", "-prescribed_on"]),
            models.Index(fields=["tenant", "patient_phone"]),
        ]

    def __str__(self) -> str:
        return f"{self.patient_name} — {self.prescriber_id} on {self.prescribed_on}"

    def is_valid_on(self, on_date: date) -> bool:
        if on_date < self.prescribed_on:
            return False
        return self.valid_until is None or on_date <= self.valid_until

    def default_validity(self, *, days: int = 90) -> date:
        return self.prescribed_on + timedelta(days=days)
