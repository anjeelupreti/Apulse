from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def sync_after_migrate(**_kwargs: Any) -> None:
    from .services import sync_schedule_rules

    sync_schedule_rules()


class PharmacyConfig(AppConfig):
    name = "modules.pharmacy"
    label = "pharmacy"
    verbose_name = "Pharmacy"

    def ready(self) -> Any:
        from core.purchasing import extensions as purchasing
        from core.sales import extensions as sales

        from . import register
        from .dispensing import refuse_unprescribed_medicines

        # Core knows nothing about drug schedules or narcotics registers; it just runs whatever
        # has been registered against the points it offers.
        sales.register_issue_validator(refuse_unprescribed_medicines)
        sales.register_issued_hook(register.record_dispensing)
        sales.register_cancelled_hook(register.record_sale_cancellation)
        sales.register_credit_note_hook(register.record_return)
        purchasing.register_posted_hook(register.record_receipt)
        purchasing.register_cancelled_hook(register.record_receipt_cancellation)

        from kernel.audit.tracking import track

        from .models import MedicineProfile, Prescription, ScheduleRule

        # Not the register: it is append-only in the database and is its own log. These three are
        # edited, and a drug schedule quietly changing is the change that matters most here.
        for model in (MedicineProfile, Prescription, ScheduleRule):
            track(model)

        post_migrate.connect(sync_after_migrate, sender=self)
