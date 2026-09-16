from typing import Any

from django.apps import AppConfig


class NumberingConfig(AppConfig):
    name = "kernel.numbering"
    label = "numbering"
    verbose_name = "Document numbering"

    def ready(self) -> Any:
        from . import registry

        registry.autodiscover()
