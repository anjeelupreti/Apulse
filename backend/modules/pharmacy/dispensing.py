"""The check that runs before a bill is issued.

Registered with core.sales at startup. Core calls it without knowing what a drug schedule is.
"""

from typing import Any

from shared.errors import DomainError

from . import errors
from .models import DrugSchedule, MedicineProfile
from .services import prescriptions_for, rule_for


def refuse_unprescribed_medicines(invoice: Any) -> None:
    """Refuse a sale of a scheduled medicine with no valid prescription.

    Checked against the rule in force on the invoice date, not today's rule, so a backdated sale
    is judged by what applied when it happened.
    """
    profiles = _profiles_on(invoice)
    if not profiles:
        return

    prescriptions = prescriptions_for(invoice)
    valid = [item for item in prescriptions if item.is_valid_on(invoice.invoice_date)]

    for profile in profiles:
        rule = rule_for(profile.schedule, on_date=invoice.invoice_date)
        if rule is None or not rule.requires_prescription:
            continue

        if profile.schedule == DrugSchedule.UNCLASSIFIED:
            raise DomainError(
                errors.MEDICINE_NOT_CLASSIFIED,
                f"{profile.item.name} has no drug group set.",
            )

        if not prescriptions:
            raise DomainError(
                errors.PRESCRIPTION_REQUIRED,
                f"{profile.item.name} needs a prescription.",
            )
        if not valid:
            raise DomainError(
                errors.PRESCRIPTION_EXPIRED,
                f"The prescription presented for {profile.item.name} is out of date.",
            )
        if rule.requires_prescriber_registration and not any(
            item.prescriber.registration_number for item in valid
        ):
            raise DomainError(
                errors.PRESCRIBER_REGISTRATION_REQUIRED,
                f"{profile.item.name} requires the prescriber's registration number.",
            )


def _profiles_on(invoice: Any) -> list[MedicineProfile]:
    item_ids = invoice.lines.values_list("item_id", flat=True)
    return list(MedicineProfile.objects.filter(item_id__in=item_ids).select_related("item"))


def requirements_for(invoice: Any) -> dict[str, Any]:
    """What this bill needs before it can be issued, for the counter to show as it is built."""
    profiles = _profiles_on(invoice)
    needs_prescription: list[str] = []
    needs_register: list[str] = []

    for profile in profiles:
        rule = rule_for(profile.schedule, on_date=invoice.invoice_date)
        if rule is None:
            continue
        if rule.requires_prescription:
            needs_prescription.append(profile.item.name)
        if rule.requires_register_entry:
            needs_register.append(profile.item.name)

    return {
        "prescription_required_for": needs_prescription,
        "register_entry_required_for": needs_register,
        "has_prescription": bool(prescriptions_for(invoice)),
    }
