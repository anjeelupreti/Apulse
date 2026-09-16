from rest_framework.routers import DefaultRouter

from .views import CreditNoteViewSet, InvoiceViewSet

app_name = "sales"

router = DefaultRouter()
router.register("sales/invoices", InvoiceViewSet, basename="sales-invoice")
router.register("sales/credit-notes", CreditNoteViewSet, basename="sales-credit-note")

urlpatterns = router.urls
