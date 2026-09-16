from django.apps import AppConfig


class TenancyConfig(AppConfig):
    name = "kernel.tenancy"
    label = "tenancy"
    verbose_name = "Tenancy"

    def ready(self) -> None:
        from kernel.audit.tracking import track

        from .models import Branch, LegalEntity, Location

        # A branch's DDA licence number and its expiry date live here, and the PAN lives on the
        # legal entity. All of them are read straight off the record by an inspection, which
        # expects them to have said the same thing all along, so every change is dated and named.
        for model in (LegalEntity, Branch, Location):
            track(model)
