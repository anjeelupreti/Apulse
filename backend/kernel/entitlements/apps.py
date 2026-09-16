from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def sync_after_migrate(**_kwargs: Any) -> None:
    """Keep the module tables in step with the code, the way Django syncs permissions.

    Doing it here rather than in a data migration means the tables reflect the manifests as they
    are *now*, instead of replaying whatever they looked like when a migration was written.
    """
    from .services import sync_modules

    sync_modules()


class EntitlementsConfig(AppConfig):
    name = "kernel.entitlements"
    label = "entitlements"
    verbose_name = "Modules and entitlements"

    def ready(self) -> Any:
        from . import manifest

        manifest.autodiscover()
        post_migrate.connect(sync_after_migrate, sender=self)
