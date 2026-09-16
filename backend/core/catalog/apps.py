from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def sync_after_migrate(**_kwargs: Any) -> None:
    from .services import sync_units

    sync_units()


class CatalogConfig(AppConfig):
    name = "core.catalog"
    label = "catalog"
    verbose_name = "Item catalogue"

    def ready(self) -> Any:
        post_migrate.connect(sync_after_migrate, sender=self)
