from rest_framework.routers import DefaultRouter

from .views import (
    CreditNoteRefundViewSet,
    CustomerLedgerViewSet,
    InvoicePaymentViewSet,
    PaymentModeViewSet,
    PaymentViewSet,
    ShiftViewSet,
)

app_name = "payments"

router = DefaultRouter()
router.register("payments/modes", PaymentModeViewSet, basename="payment-mode")
router.register("payments/payments", PaymentViewSet, basename="payment")
router.register("payments/shifts", ShiftViewSet, basename="shift")
router.register("customers/ledger", CustomerLedgerViewSet, basename="customer-ledger")
# Money against a document hangs off that document, not off a payments collection.
router.register("sales/invoices", InvoicePaymentViewSet, basename="invoice-payment")
router.register("sales/credit-notes", CreditNoteRefundViewSet, basename="credit-note-refund")

urlpatterns = router.urls
