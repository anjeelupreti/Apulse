"""The counter, over HTTP.

The shape follows the documents rather than the tables: a bill is *started*, *added to* and
*issued*, because those are three different things with three different levels of trust and three
different consequences, and a single `PATCH /invoices/{id}` that sometimes takes a number and moves
stock would hide all of that.

Every write goes through the service layer. None of these views contain a rule; they translate
between HTTP and a service call, and the rules stay where they can be tested without a request.
"""

from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from core.catalog.models import Item, UnitOfMeasure
from core.parties.models import Party
from core.sales import permissions as perms
from core.sales import returns, services
from core.sales.models import CreditNote, SalesInvoice
from kernel.foundation.api.idempotency import idempotent
from kernel.foundation.api.viewsets import ReadOnlyTenantViewSet, TenantAPIView
from kernel.tenancy.models import Branch, Location

from .serializers import (
    AddLineSerializer,
    CancelInvoiceSerializer,
    CreditNoteSerializer,
    CreditWholeInvoiceSerializer,
    InvoiceLineSerializer,
    InvoiceSerializer,
    StartInvoiceSerializer,
)


class InvoiceViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, TenantAPIView
):
    """Bills: list, read, start, add to, issue, cancel."""

    serializer_class = InvoiceSerializer
    required_permissions = (perms.INVOICE_VIEW.code,)
    branch_scope_permission = perms.INVOICE_VIEW.code
    date_field = "invoice_date"
    search_fields = ("number", "customer_name", "customer_phone")
    ordering_fields = ("invoice_date", "created_at", "payable_amount", "number")
    ordering = ("-invoice_date", "-created_at")
    action_permissions = {
        "create": (perms.INVOICE_BUILD.code,),
        "add_line": (perms.INVOICE_BUILD.code,),
        "issue": (perms.INVOICE_ISSUE.code,),
        "cancel": (perms.INVOICE_CANCEL.code,),
        "reprint": (perms.INVOICE_REPRINT.code,),
        "credit": (perms.CREDIT_NOTE_ISSUE.code,),
    }

    def get_queryset(self) -> QuerySet[SalesInvoice]:
        return SalesInvoice.objects.select_related(
            "branch", "location", "customer"
        ).prefetch_related("lines__item", "lines__unit", "lines__allocations__batch")

    def _reread(self, invoice: SalesInvoice) -> SalesInvoice:
        """Serialise from a fresh read, not from the object the service handed back.

        `get_object()` prefetches lines and their batch allocations. Issuing then creates those
        allocations — so the instance in hand still carries the prefetch cache from *before* the
        work, and rendering it would report a bill with no batches on it.
        """
        return self.get_queryset().get(pk=invoice.pk)

    # ----------------------------------------------------------------- starting a bill
    @extend_schema(
        request=StartInvoiceSerializer,
        responses={201: InvoiceSerializer},
        description="Open a draft. Moves no stock and takes no number until it is issued.",
    )
    @idempotent()
    def create(
        self,
        request: Request,
        *args: Any,  # noqa: ARG002 — DRF passes them; the payload says everything
        **kwargs: Any,  # noqa: ARG002
    ) -> Response:
        payload = StartInvoiceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        invoice = services.start_invoice(
            branch=get_object_or_404(Branch, pk=data["branch"]),
            location=get_object_or_404(Location, pk=data["location"]),
            invoice_date=data.get("invoice_date"),
            customer=(
                get_object_or_404(Party, pk=data["customer"]) if data.get("customer") else None
            ),
            customer_name=data.get("customer_name", ""),
            customer_phone=data.get("customer_phone", ""),
            prices_include_tax=data.get("prices_include_tax", True),
        )
        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=AddLineSerializer,
        responses={201: InvoiceLineSerializer},
        description=(
            "Put an item on a draft. Priced from the batch on the shelf unless a rate is given; "
            "above the printed maximum is refused."
        ),
    )
    @action(detail=True, methods=["post"], url_path="lines")
    @idempotent()
    def add_line(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        payload = AddLineSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        line = services.add_line(
            self.get_object(),
            item=get_object_or_404(Item, pk=data["item"]),
            quantity=data["quantity"],
            unit=(get_object_or_404(UnitOfMeasure, pk=data["unit"]) if data.get("unit") else None),
            rate=data.get("rate"),
            discount_percent=data.get("discount_percent") or 0,
        )
        return Response(InvoiceLineSerializer(line).data, status=status.HTTP_201_CREATED)

    # ----------------------------------------------------------------- issuing it
    @extend_schema(
        request=None,
        responses={
            200: InvoiceSerializer,
            409: OpenApiResponse(description="Already issued, or the same request is in flight."),
            422: OpenApiResponse(
                description="A rule refused it — no prescription, or expired stock."
            ),
        },
        description=(
            "Take the number, move the stock, fix the totals. Needs an Idempotency-Key: a retry "
            "over a bad connection must not bill the customer twice."
        ),
    )
    @action(detail=True, methods=["post"])
    @idempotent(required=True)
    def issue(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        issued = services.issue_invoice(self.get_object(), actor=self.audit_actor())
        return Response(InvoiceSerializer(self._reread(issued.invoice)).data)

    @extend_schema(
        request=CancelInvoiceSerializer,
        responses={200: InvoiceSerializer},
        description=(
            "Reverse the stock, keep the number, and issue the credit note that evidences it."
        ),
    )
    @action(detail=True, methods=["post"])
    @idempotent(required=True)
    def cancel(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        payload = CancelInvoiceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        invoice = services.cancel_invoice(
            self.get_object(),
            reason=payload.validated_data["reason"],
            actor=self.audit_actor(),
        )
        return Response(InvoiceSerializer(self._reread(invoice)).data)

    # ----------------------------------------------------------------- crediting it
    @extend_schema(
        request=CreditWholeInvoiceSerializer,
        responses={201: CreditNoteSerializer},
        description=(
            "Credit the whole bill in one step. `confirmed` must be true: this issues a numbered "
            "tax document and moves stock, and the only way back is another credit note."
        ),
    )
    @action(detail=True, methods=["post"], url_path="credit-note")
    @idempotent(required=True)
    def credit(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        payload = CreditWholeInvoiceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        issued = returns.credit_invoice(
            self.get_object(),
            reason=data["reason"],
            confirmed=data["confirmed"],
            kind=data["kind"],
            reason_code=data["reason_code"],
            destination=data["destination"],
            actor=self.audit_actor(),
        )
        return Response(
            CreditNoteSerializer(issued.credit_note).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        request=None,
        responses={200: InvoiceSerializer},
        description="Count a print. Anything after the first is marked as a copy.",
    )
    @action(detail=True, methods=["post"])
    def reprint(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        invoice = self.get_object()
        services.record_print(invoice)
        return Response(InvoiceSerializer(self._reread(invoice)).data)


class CreditNoteViewSet(ReadOnlyTenantViewSet):
    """Credit notes are created against their invoice, so this is read-only."""

    serializer_class = CreditNoteSerializer
    required_permissions = (perms.CREDIT_NOTE_VIEW.code,)
    branch_scope_permission = perms.CREDIT_NOTE_VIEW.code
    date_field = "note_date"
    search_fields = ("number", "invoice__number", "reason")
    ordering_fields = ("note_date", "created_at", "payable_amount")
    ordering = ("-note_date", "-created_at")

    def get_queryset(self) -> QuerySet[CreditNote]:
        return CreditNote.objects.select_related("invoice", "branch").prefetch_related(
            "lines__item", "lines__batch"
        )
