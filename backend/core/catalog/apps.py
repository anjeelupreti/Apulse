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
        from kernel.audit.tracking import track

        from .models import Item, ItemBarcode, ItemCategory, ItemUnit, Manufacturer

        # What a product is, what it costs and what it is called are all things somebody could
        # change quietly, so every one of them leaves an entry.
        for model in (Item, ItemUnit, ItemBarcode, ItemCategory, Manufacturer):
            track(model)

        post_migrate.connect(sync_after_migrate, sender=self)
