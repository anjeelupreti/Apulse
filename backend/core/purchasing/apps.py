from django.apps import AppConfig


class PurchasingConfig(AppConfig):
    name = "core.purchasing"
    label = "purchasing"
    verbose_name = "Purchasing"

    def ready(self) -> None:
        from kernel.audit.tracking import track

        from .models import GoodsReceipt, GoodsReceiptLine

        track(GoodsReceipt)
        track(GoodsReceiptLine)
