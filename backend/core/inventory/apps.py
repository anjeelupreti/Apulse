from django.apps import AppConfig


class InventoryConfig(AppConfig):
    name = "core.inventory"
    label = "inventory"
    verbose_name = "Inventory"

    def ready(self) -> None:
        from kernel.audit.tracking import track

        from .models import Batch

        # Batches only. The stock ledger **is** the inventory log — append-only in the database,
        # carrying the actor, the document and the reason — and auditing a log would write every
        # movement twice. Balances are a running total derived from it, not a record of anything.
        # A batch is different: its expiry, its printed price and its status are the facts a
        # recall and an inspection both turn on, and they are edited rather than appended.
        track(Batch)
