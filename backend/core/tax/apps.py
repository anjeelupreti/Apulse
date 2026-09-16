from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def sync_after_migrate(**_kwargs: Any) -> None:
    from .services import sync_tax_categories

    sync_tax_categories()


class TaxConfig(AppConfig):
    name = "core.tax"
    label = "tax"
    verbose_name = "Tax"

    def ready(self) -> Any:
        post_migrate.connect(sync_after_migrate, sender=self)
