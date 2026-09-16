from django.apps import AppConfig


class PartiesConfig(AppConfig):
    name = "core.parties"
    label = "parties"
    verbose_name = "Customers and suppliers"

    def ready(self) -> None:
        from kernel.audit.tracking import track

        from .models import Party

        # A credit limit or a PAN changing is worth a line in the trail.
        track(Party)
