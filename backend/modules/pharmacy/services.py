"""Seeding the drug rules, and looking up which rule was in force."""

from datetime import date
from typing import Any

import structlog
from django.db import transaction

from .models import DrugSchedule, MedicineProfile, Prescription, ScheduleRule

logger = structlog.get_logger(__name__)

#: The Drug Act, 2035 came into force in 1978. Rules are dated from there so a sale can always be
#: judged by the rule that applied on the day it happened.
RULES_START = date(1978, 9, 17)

#: What the research found (see docs/research/nepal-regulatory-findings.md). Both क and ख require
#: a prescription; ग is supplied on a pharmacist's advice. **Secondary sources** — CR-DDA-01 must
#: be closed against the Act and DDA's own lists before a real pharmacy relies on this.
SEED_RULES: tuple[dict[str, Any], ...] = (
    {
        "schedule": DrugSchedule.KA,
        "requires_prescription": True,
        "requires_prescriber_registration": True,
        "requires_register_entry": True,
        "requires_pharmacist": True,
        "source_note": "Samuha Ka: narcotics and psychotropics. Unverified — CR-DDA-01.",
    },
    {
        "schedule": DrugSchedule.KHA,
        "requires_prescription": True,
        "requires_prescriber_registration": True,
        "requires_pharmacist": True,
        "source_note": "Samuha Kha: prescription required. Unverified — CR-DDA-01.",
    },
    {
        "schedule": DrugSchedule.GA,
        "requires_pharmacist": True,
        "source_note": "Samuha Ga: supplied on a pharmacist's advice. Unverified — CR-DDA-01.",
    },
    {
        "schedule": DrugSchedule.UNCLASSIFIED,
        "requires_prescription": True,
        "requires_pharmacist": True,
        "source_note": (
            "Not a legal category. An unclassified medicine is treated as restricted, because "
            "guessing the other way means handing over a controlled drug by mistake."
        ),
    },
)


@transaction.atomic
def sync_schedule_rules() -> int:
    """Create the rules if they are not there. Existing rules are never rewritten.

    A DDA notice that changes a requirement is entered as a *new* dated rule, so what was true
    last year stays readable.
    """
    for seed in SEED_RULES:
        ScheduleRule.objects.get_or_create(
            schedule=seed["schedule"],
            effective_from=RULES_START,
            defaults={
                "requires_prescription": seed.get("requires_prescription", False),
                "requires_prescriber_registration": seed.get(
                    "requires_prescriber_registration", False
                ),
                "requires_register_entry": seed.get("requires_register_entry", False),
                "requires_pharmacist": seed.get("requires_pharmacist", False),
                "max_days_supply": seed.get("max_days_supply", 0),
                "source_note": seed.get("source_note", ""),
            },
        )
    return len(SEED_RULES)


def rule_for(schedule: str, *, on_date: date) -> ScheduleRule | None:
    """The rule in force for a schedule on a date."""
    from django.db.models import Q

    return (
        ScheduleRule.objects.filter(schedule=schedule, effective_from__lte=on_date)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
        .order_by("-effective_from")
        .first()
    )


@transaction.atomic
def classify(profile: MedicineProfile, schedule: str, *, reason: str = "") -> MedicineProfile:
    """Set a medicine's drug group."""
    from kernel.audit import services as audit
    from kernel.audit import tracking
    from kernel.audit.models import AuditAction

    previous = profile.schedule
    with tracking.paused():
        profile.schedule = schedule
        profile.is_narcotic = schedule == DrugSchedule.KA
        profile.save(update_fields=["schedule", "is_narcotic", "updated_at"])

    audit.record(
        action=AuditAction.UPDATE,
        entity=profile,
        entity_label=str(profile),
        changes={"schedule": {"from": previous, "to": schedule}},
        reason=reason,
    )
    logger.info("medicine_classified", medicine=str(profile), schedule=schedule)
    return profile


def prescriptions_for(invoice: Any) -> list[Prescription]:
    return list(Prescription.objects.filter(invoice=invoice).select_related("prescriber"))
