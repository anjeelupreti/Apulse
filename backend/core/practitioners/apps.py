from django.apps import AppConfig


class PractitionersConfig(AppConfig):
    name = "core.practitioners"
    label = "practitioners"
    verbose_name = "Practitioners"

    def ready(self) -> None:
        from kernel.audit.tracking import track

        from .models import Practitioner

        # A registration number appearing on a prescriber who had none is exactly the change an
        # inspection wants to see dated and attributed.
        track(Practitioner)
