"""Medicines, the rules that govern them, and the prescriptions they are dispensed against."""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
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


class RegisterEntryType(models.TextChoices):
    """Why a controlled drug moved. Mirrors what a paper register's columns say."""

    OPENING = "opening", _("Opening balance")
    RECEIPT = "receipt", _("Received from supplier")
    DISPENSED = "dispensed", _("Dispensed to a patient")
    RETURN_IN = "return_in", _("Returned by a patient")
    RETURN_OUT = "return_out", _("Returned to supplier")
    DESTROYED = "destroyed", _("Destroyed or written off")
    ADJUSTMENT = "adjustment", _("Adjustment after a physical count")
    CORRECTION = "correction", _("Correction of an earlier entry")


class NarcoticRegisterEntry(TenantScopedModel):
    """One line of the controlled-drug register. Append-only: see migration 0004.

    The Narcotic Drugs (Control) Act, 2033 requires a seller to keep records in a prescribed
    format with the doctor's prescription attached. The prescribed format itself is still to be
    obtained — CR-DDA-02 — so the columns here are what the Act and DDA practice imply rather than
    a transcription of the official page. Changing a column later is a migration; losing a
    movement is not recoverable, so everything a register page could need is captured now.

    Names are **copied in as text** as well as linked. A register page has to read a year later
    exactly as it read on the day, and a practitioner record that is corrected in 2027 must not
    quietly rewrite what a 2026 page says.

    Nothing here is ever edited. A mistake is corrected by a `CORRECTION` entry that points at
    what it corrects and says why — which is how a paper register is corrected too, with the
    original still legible under the line through it.
    """

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    location = models.ForeignKey(
        "tenancy.Location", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        "inventory.Batch", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    entry_type = models.CharField(max_length=20, choices=RegisterEntryType.choices, db_index=True)
    #: Signed, in the item's base units. Positive into the cabinet, negative out of it.
    quantity = models.DecimalField(max_digits=18, decimal_places=3)
    #: The running balance after this entry, for this branch, item and batch. Stored rather than
    #: derived: a register page is read as a column of balances, and a page that recomputes itself
    #: differently each time it is printed is not evidence of anything.
    balance_after = models.DecimalField(max_digits=18, decimal_places=3)

    occurred_on = models.DateField(help_text=_("The business date, which may not be today."))

    # --- the patient side
    patient_name = models.CharField(max_length=200, blank=True)
    patient_address = models.CharField(max_length=300, blank=True)
    patient_identity_number = models.CharField(
        max_length=60, blank=True, help_text=_("Citizenship or other identity document shown.")
    )
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="register_entries",
    )
    prescriber = models.ForeignKey(
        "practitioners.Practitioner",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    prescriber_name = models.CharField(max_length=200, blank=True)
    prescriber_registration_number = models.CharField(max_length=60, blank=True)

    # --- the supplier side
    supplier_name = models.CharField(max_length=200, blank=True)
    supplier_invoice_number = models.CharField(max_length=60, blank=True)

    # --- who did it
    dispensed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    dispensed_by_name = models.CharField(max_length=200, blank=True)
    dispensed_by_registration_number = models.CharField(
        max_length=60, blank=True, help_text=_("The pharmacist's council registration.")
    )
    witness_name = models.CharField(
        max_length=200, blank=True, help_text=_("Required for destruction and adjustments.")
    )
    #: Where the signature image or the scanned prescription lives. A real file reference with M2.7.
    signature_reference = models.CharField(max_length=300, blank=True)

    # --- what caused it
    document_type = models.CharField(max_length=60, blank=True)
    document_id = models.CharField(max_length=64, blank=True)
    document_number = models.CharField(max_length=60, blank=True)
    corrects = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="corrected_by"
    )
    reason = models.CharField(max_length=300, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name_plural = "narcotic register entries"
        ordering = ["occurred_on", "created_at"]
        indexes = [
            models.Index(fields=["tenant", "branch", "item", "occurred_on"]),
            models.Index(fields=["tenant", "item", "batch"]),
            models.Index(fields=["tenant", "document_type", "document_id"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(quantity=0), name="pharmacy_register_entry_is_not_zero"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_entry_type_display()} {self.quantity} on {self.occurred_on}"


class NarcoticRegisterBalance(TenantScopedModel):
    """What the register says should be in the cabinet, per branch, drug and batch.

    A running total kept so the next entry does not have to add up the whole register. The entries
    are the truth; `reconcile_register()` reports any disagreement rather than correcting it,
    because a balance that drifted means something wrote to the register outside this module.
    """

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        "inventory.Batch", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=3, default=Decimal("0"))

    class Meta:
        ordering = ["item", "batch"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "branch", "item", "batch"],
                name="pharmacy_one_register_balance_per_batch",
                nulls_distinct=False,
            )
        ]

    def __str__(self) -> str:
        return f"{self.quantity} of {self.item_id} at {self.branch_id}"
