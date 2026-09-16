from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    name = "core.payments"
    label = "payments"
    verbose_name = "Payments and till"

    def ready(self) -> None:
        from kernel.audit.tracking import track

        from .models import CashierShift, PaymentMode

        # Not Payment or CashMovement: both are append-only in the database and both already
        # carry who, when, why and against what. A shift is different — it opens, takes a count
        # and gets signed off — so every one of those steps leaves an entry.
        track(PaymentMode)
        track(CashierShift)
