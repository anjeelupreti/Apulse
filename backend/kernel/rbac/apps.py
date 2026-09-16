from typing import Any

from django.apps import AppConfig


class RbacConfig(AppConfig):
    name = "kernel.rbac"
    label = "rbac"
    verbose_name = "Access control"

    def ready(self) -> Any:
        # Importing each app's `permissions` module is what fills the registry. Without this the
        # registry would be empty until something happened to import those modules.
        from kernel.rbac import registry

        registry.autodiscover()
