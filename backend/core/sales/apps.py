from django.apps import AppConfig


class SalesConfig(AppConfig):
    name = "core.sales"
    label = "sales"
    verbose_name = "Sales"

    def ready(self) -> None:
        from kernel.audit.tracking import track

        from .models import CreditNote, CreditNoteLine, SalesInvoice, SalesInvoiceLine

        # Including drafts. A bill that was built, altered and abandoned before anybody paid is
        # not visible anywhere else, and "what was on it before it was changed" is a question
        # that gets asked after the money has gone missing, not before.
        for model in (SalesInvoice, SalesInvoiceLine, CreditNote, CreditNoteLine):
            track(model)
