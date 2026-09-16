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
        from core.sales.validators import register_issue_validator

        from .dispensing import refuse_unprescribed_medicines

        # Core knows nothing about drug schedules; it just runs whatever checks are registered.
        register_issue_validator(refuse_unprescribed_medicines)
        post_migrate.connect(sync_after_migrate, sender=self)
