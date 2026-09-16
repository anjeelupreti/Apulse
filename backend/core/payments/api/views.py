"""Taking money and counting the till, over HTTP."""

from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from core.parties.models import Party
from core.payments import credit, services
from core.payments import permissions as perms
from core.payments.models import CashierShift, Payment, PaymentMode
from core.sales.models import CreditNote, SalesInvoice
from kernel.foundation.api.idempotency import idempotent
from kernel.foundation.api.viewsets import ReadOnlyTenantViewSet, TenantAPIView
from kernel.tenancy.models import Branch, Location

from .serializers import (
    CashMovementInputSerializer,
    CashMovementSerializer,
    CloseShiftSerializer,
    CreditDecisionSerializer,
    OpenShiftSerializer,
    PaymentModeSerializer,
    PaymentSerializer,
    ReceiveAgainstSerializer,
    RefundSerializer,
    SettleInvoiceSerializer,
    ShiftSerializer,
    ShiftSummarySerializer,
    StatementLineSerializer,
)


class PaymentModeViewSet(ReadOnlyTenantViewSet):
    """The buttons this pharmacy accepts. What the payment screen is built from."""

    serializer_class = PaymentModeSerializer
    required_permissions = (perms.PAYMENT_VIEW.code,)
    branch_scope_permission = None
    ordering = ("sort_order", "name")

    def get_queryset(self) -> QuerySet[PaymentMode]:
        queryset = PaymentMode.objects.all()
        if self.request.query_params.get("include_inactive") != "true":
            queryset = queryset.filter(is_active=True)
        return queryset


class PaymentViewSet(ReadOnlyTenantViewSet):
    """Payments are recorded against the document they settle, so this is read-only."""

    serializer_class = PaymentSerializer
    required_permissions = (perms.PAYMENT_VIEW.code,)
    date_field = "received_on"
    search_fields = ("reference", "document_number")
    ordering_fields = ("received_on", "created_at", "amount")
    ordering = ("-received_on", "-created_at")

    def get_queryset(self) -> QuerySet[Payment]:
        return Payment.objects.select_related("mode", "party", "branch")


class InvoicePaymentViewSet(TenantAPIView):
    """Settling a bill, and giving money back against a credit note."""

    serializer_class = PaymentSerializer
    required_permissions = (perms.PAYMENT_VIEW.code,)
    action_permissions = {
        "settle": (perms.PAYMENT_TAKE.code,),
        "receive": (perms.PAYMENT_TAKE.code,),
        "refund": (perms.PAYMENT_REFUND.code,),
        "credit_check": (perms.LEDGER_VIEW.code,),
    }

    def get_queryset(self) -> QuerySet[SalesInvoice]:
        return SalesInvoice.objects.select_related("branch", "customer")

    def _modes(self, tenders: list[dict[str, Any]]) -> list[tuple[PaymentMode, Any]]:
        return [
            (get_object_or_404(PaymentMode, pk=tender["mode"]), tender["amount"])
            for tender in tenders
        ]

    @extend_schema(
        request=SettleInvoiceSerializer,
        responses={201: PaymentSerializer(many=True)},
        description=(
            "Settle a bill, across as many methods as it takes. Checked against what is left to "
            "settle, so a mistyped second tender cannot leave money nobody claimed."
        ),
    )
    @action(detail=True, methods=["post"], url_path="payments")
    @idempotent(required=True)
    def settle(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        payload = SettleInvoiceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        payments = services.settle_invoice(
            self.get_object(),
            tenders=self._modes(data["tenders"]),
            shift=(
                get_object_or_404(CashierShift, pk=data["shift"]) if data.get("shift") else None
            ),
            tendered_cash=data.get("tendered_cash"),
            references={
                get_object_or_404(PaymentMode, pk=tender["mode"]).code: tender.get("reference", "")
                for tender in data["tenders"]
                if tender.get("reference")
            },
            actor=self.audit_actor(),
            override_reason=data.get("override_reason", ""),
            override_by=self.audit_actor(),
        )
        return Response(PaymentSerializer(payments, many=True).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=ReceiveAgainstSerializer,
        responses={201: PaymentSerializer},
        description=(
            "Take money against a bill that is already outstanding — the cheque that arrives next "
            "month. Checked against what is still owed, not against what is left to tender."
        ),
    )
    @action(detail=True, methods=["post"], url_path="receipts")
    @idempotent(required=True)
    def receive(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        payload = ReceiveAgainstSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        payment = services.receive_against(
            self.get_object(),
            mode=get_object_or_404(PaymentMode, pk=data["mode"]),
            amount=data["amount"],
            shift=(
                get_object_or_404(CashierShift, pk=data["shift"]) if data.get("shift") else None
            ),
            reference=data.get("reference", ""),
            received_on=data.get("received_on"),
            actor=self.audit_actor(),
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[
            OpenApiParameter("amount", str, description="What is about to be put on account.")
        ],
        responses={200: CreditDecisionSerializer},
        description=(
            "The customer's credit position before anything is committed, so the counter can say "
            "what is wrong rather than reading out a refusal."
        ),
    )
    @action(detail=True, methods=["get"], url_path="credit-check")
    def credit_check(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        invoice = self.get_object()
        if invoice.customer is None:
            from core.payments import errors
            from shared.errors import DomainError

            raise DomainError(errors.CREDIT_NEEDS_A_NAMED_CUSTOMER)

        decision = credit.assess(
            invoice.customer,
            amount=request.query_params.get("amount") or invoice.payable_amount,
            on_date=invoice.invoice_date,
            branch=invoice.branch,
        )
        return Response(
            CreditDecisionSerializer(
                {
                    "allowed": decision.allowed,
                    "is_warning": decision.is_warning,
                    "limit": decision.limit,
                    "exposure": decision.exposure,
                    "requested": decision.requested,
                    "headroom": decision.headroom,
                    "would_exceed_by": decision.would_exceed_by,
                    "overdue_amount": decision.overdue_amount,
                    "oldest_overdue_days": decision.oldest_overdue_days,
                    "reason": decision.reason,
                }
            ).data
        )


class CreditNoteRefundViewSet(TenantAPIView):
    """Refunds go against the credit note, never against the invoice."""

    serializer_class = PaymentSerializer
    required_permissions = (perms.PAYMENT_VIEW.code,)
    action_permissions = {"refund": (perms.PAYMENT_REFUND.code,)}

    def get_queryset(self) -> QuerySet[CreditNote]:
        return CreditNote.objects.select_related("branch", "invoice")

    @extend_schema(
        request=RefundSerializer,
        responses={201: PaymentSerializer},
        description=(
            "Give money back against a credit note. The note is what says money is owed; a refund "
            "with nothing behind it is indistinguishable from a till being emptied."
        ),
    )
    @action(detail=True, methods=["post"], url_path="refunds")
    @idempotent(required=True)
    def refund(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        payload = RefundSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        payment = services.refund(
            self.get_object(),
            mode=get_object_or_404(PaymentMode, pk=data["mode"]),
            amount=data.get("amount"),
            shift=(
                get_object_or_404(CashierShift, pk=data["shift"]) if data.get("shift") else None
            ),
            reference=data.get("reference", ""),
            actor=self.audit_actor(),
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class ShiftViewSet(TenantAPIView):
    """The till: open it, move cash in and out of it, count it, close it, sign it off."""

    serializer_class = ShiftSerializer
    required_permissions = (perms.SHIFT_VIEW.code,)
    date_field = "business_date"
    ordering_fields = ("business_date", "opened_at")
    ordering = ("-business_date", "-opened_at")
    action_permissions = {
        "create": (perms.SHIFT_OPEN.code,),
        "close": (perms.SHIFT_CLOSE.code,),
        "approve": (perms.SHIFT_APPROVE.code,),
        "cash": (perms.PAYMENT_TAKE.code,),
    }

    def get_queryset(self) -> QuerySet[CashierShift]:
        return CashierShift.objects.select_related(
            "branch", "location", "cashier", "closed_by", "approved_by"
        ).prefetch_related("cash_movements")

    def list(
        self,
        request: Request,  # noqa: ARG002 — DRF's signature; the filters read it themselves
        *args: Any,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> Response:
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(ShiftSerializer(page, many=True).data)

    def retrieve(
        self,
        request: Request,  # noqa: ARG002 — DRF's signature; the pk is in the URL
        *args: Any,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> Response:
        return Response(ShiftSerializer(self.get_object()).data)

    @extend_schema(
        request=OpenShiftSerializer,
        responses={201: ShiftSerializer},
        description="Open the till. One per counter: a shared drawer belongs to nobody.",
    )
    @idempotent()
    def create(
        self,
        request: Request,
        *args: Any,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> Response:
        payload = OpenShiftSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        shift = services.open_shift(
            branch=get_object_or_404(Branch, pk=data["branch"]),
            location=get_object_or_404(Location, pk=data["location"]),
            cashier=self.audit_actor(),
            opening_float=data.get("opening_float"),
            business_date=data.get("business_date"),
            note=data.get("note", ""),
        )
        return Response(ShiftSerializer(shift).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={200: ShiftSummarySerializer},
        description="What the drawer should hold, and what came in by which method.",
    )
    @action(detail=True, methods=["get"])
    def summary(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        summary = services.summarise(self.get_object())
        return Response(
            ShiftSummarySerializer(
                {
                    "opening_float": summary.opening_float,
                    "cash_received": summary.cash_received,
                    "cash_refunded": summary.cash_refunded,
                    "cash_movements": summary.cash_movements,
                    "expected_cash": summary.expected_cash,
                    "by_mode": summary.by_mode,
                    "payment_count": summary.payment_count,
                }
            ).data
        )

    @extend_schema(
        request=CashMovementInputSerializer,
        responses={201: CashMovementSerializer},
        description="Cash in or out for something that is not a sale. Money out needs a witness.",
    )
    @action(detail=True, methods=["post"], url_path="cash")
    @idempotent()
    def cash(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        payload = CashMovementInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        movement = services.record_cash_movement(
            self.get_object(),
            kind=data["kind"],
            amount=data["amount"],
            reason=data["reason"],
            witness_name=data.get("witness_name", ""),
            reference=data.get("reference", ""),
            actor=self.audit_actor(),
        )
        return Response(CashMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=CloseShiftSerializer,
        responses={200: ShiftSerializer},
        description=(
            "Count the drawer and close it. The difference is recorded, never adjusted away; "
            "anything beyond the tolerance needs an explanation first."
        ),
    )
    @action(detail=True, methods=["post"])
    @idempotent(required=True)
    def close(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        payload = CloseShiftSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        shift = services.close_shift(
            self.get_object(),
            counts=payload.as_mapping(),
            actor=self.audit_actor(),
            variance_reason=payload.validated_data.get("variance_reason", ""),
            note=payload.validated_data.get("note", ""),
        )
        return Response(ShiftSerializer(shift).data)

    @extend_schema(
        request=None,
        responses={200: ShiftSerializer},
        description=(
            "A supervisor signs off a counted till. A cashier approving their own count is one "
            "person, however many buttons they press."
        ),
    )
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        shift = services.approve_shift(self.get_object(), approver=self.audit_actor())
        return Response(ShiftSerializer(shift).data)


class CustomerLedgerViewSet(TenantAPIView):
    """What a customer owes, and the statement behind it."""

    serializer_class = StatementLineSerializer
    required_permissions = (perms.LEDGER_VIEW.code,)
    branch_scope_permission = None

    def get_queryset(self) -> QuerySet[Party]:
        return Party.objects.filter(is_customer=True)

    @extend_schema(
        parameters=[
            OpenApiParameter("date_from", str, description="Statement start (inclusive)."),
            OpenApiParameter("date_to", str, description="Statement end (inclusive)."),
        ],
        responses={200: StatementLineSerializer(many=True)},
        description=(
            "Opening balance, bills as debits, payments and credit notes as credits, and a "
            "running balance — ordered by business date, which is the order their own file is in."
        ),
    )
    @action(detail=True, methods=["get"])
    def statement(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        from datetime import date

        party = self.get_object()
        start = request.query_params.get("date_from") or date.min.isoformat()
        end = request.query_params.get("date_to") or date.max.isoformat()
        lines = credit.statement(
            party, start=date.fromisoformat(start), end=date.fromisoformat(end)
        )
        return Response(
            {
                "opening_balance": str(
                    credit.opening_balance(party, before=date.fromisoformat(start))
                ),
                "outstanding": str(credit.outstanding_for(party)),
                "ageing": {name: str(value) for name, value in credit.ageing(party).items()},
                "lines": StatementLineSerializer(
                    [
                        {
                            "on_date": line.on_date,
                            "kind": line.kind,
                            "reference": line.reference,
                            "description": line.description,
                            "debit": line.debit,
                            "credit": line.credit,
                            "balance": line.balance,
                        }
                        for line in lines
                    ],
                    many=True,
                ).data,
            }
        )
