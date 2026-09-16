"""What a bill looks like over the wire.

Amounts are strings, not floats. `COERCE_DECIMAL_TO_STRING` is on for the whole API, and it stays
on: a total that survives a round trip through a JSON number is a total that has been quietly
rounded by a language that does not do decimal arithmetic.
"""

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from core.sales.models import (
    CreditNote,
    CreditNoteKind,
    CreditNoteLine,
    ReturnDestination,
    ReturnReason,
    SalesInvoice,
    SalesInvoiceLine,
    SalesInvoiceLineBatch,
)


class InvoiceLineBatchSerializer(serializers.ModelSerializer[SalesInvoiceLineBatch]):
    batch_number = serializers.CharField(source="batch.number", read_only=True, default="")
    expiry_date = serializers.DateField(source="batch.expiry_date", read_only=True, default=None)

    class Meta:
        model = SalesInvoiceLineBatch
        fields = ("id", "batch", "batch_number", "expiry_date", "quantity")
        read_only_fields = fields


class InvoiceLineSerializer(serializers.ModelSerializer[SalesInvoiceLine]):
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_code = serializers.CharField(source="item.code", read_only=True)
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    allocations = InvoiceLineBatchSerializer(many=True, read_only=True)

    class Meta:
        model = SalesInvoiceLine
        fields = (
            "id",
            "item",
            "item_code",
            "item_name",
            "unit",
            "unit_name",
            "quantity",
            "base_quantity",
            "rate",
            "discount_percent",
            "tax_percentage",
            "gross_amount",
            "discount_amount",
            "taxable_amount",
            "tax_amount",
            "allocations",
        )
        read_only_fields = fields


class InvoiceSerializer(serializers.ModelSerializer[SalesInvoice]):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    amount_in_words = serializers.SerializerMethodField()
    amount_outstanding = serializers.SerializerMethodField()
    is_copy = serializers.SerializerMethodField()

    class Meta:
        model = SalesInvoice
        fields = (
            "id",
            "number",
            "fiscal_year",
            "invoice_date",
            "due_date",
            "status",
            "branch",
            "location",
            "customer",
            "customer_name",
            "customer_phone",
            "prices_include_tax",
            "gross_amount",
            "discount_amount",
            "taxable_amount",
            "tax_amount",
            "rounding_amount",
            "payable_amount",
            "amount_outstanding",
            "amount_in_words",
            "print_count",
            "is_copy",
            "issued_at",
            "cancelled_at",
            "cancelled_reason",
            "lines",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_amount_in_words(self, invoice: SalesInvoice) -> str:
        from shared.formatting import amount_in_words_en

        return amount_in_words_en(invoice.payable_amount)

    def get_amount_outstanding(self, invoice: SalesInvoice) -> str:
        from core.payments.services import amount_outstanding

        return str(amount_outstanding(invoice))

    def get_is_copy(self, invoice: SalesInvoice) -> bool:
        return invoice.print_count > 1


# --------------------------------------------------------------------------- what comes in
class StartInvoiceSerializer(serializers.Serializer[Any]):
    branch = serializers.UUIDField()
    location = serializers.UUIDField()
    invoice_date = serializers.DateField(required=False)
    customer = serializers.UUIDField(required=False, allow_null=True)
    customer_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    customer_phone = serializers.CharField(required=False, allow_blank=True, max_length=16)
    prices_include_tax = serializers.BooleanField(default=True)


class AddLineSerializer(serializers.Serializer[Any]):
    item = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=18, decimal_places=3, min_value=Decimal("0.001"))
    unit = serializers.UUIDField(required=False, allow_null=True)
    rate = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, allow_null=True
    )
    discount_percent = serializers.DecimalField(
        max_digits=6, decimal_places=3, required=False, default=Decimal("0")
    )


class CancelInvoiceSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(max_length=300)


# --------------------------------------------------------------------------- credit notes
class CreditNoteLineSerializer(serializers.ModelSerializer[CreditNoteLine]):
    item_name = serializers.CharField(source="item.name", read_only=True)
    batch_number = serializers.CharField(source="batch.number", read_only=True, default="")

    class Meta:
        model = CreditNoteLine
        fields = (
            "id",
            "invoice_line",
            "item",
            "item_name",
            "unit",
            "batch",
            "batch_number",
            "quantity",
            "rate",
            "tax_percentage",
            "gross_amount",
            "discount_amount",
            "taxable_amount",
            "tax_amount",
        )
        read_only_fields = fields


class CreditNoteSerializer(serializers.ModelSerializer[CreditNote]):
    lines = CreditNoteLineSerializer(many=True, read_only=True)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)

    class Meta:
        model = CreditNote
        fields = (
            "id",
            "number",
            "fiscal_year",
            "note_date",
            "status",
            "kind",
            "reason_code",
            "reason",
            "destination",
            "branch",
            "location",
            "invoice",
            "invoice_number",
            "gross_amount",
            "discount_amount",
            "taxable_amount",
            "tax_amount",
            "rounding_amount",
            "payable_amount",
            "lines",
            "issued_at",
            "created_at",
        )
        read_only_fields = fields


class CreditWholeInvoiceSerializer(serializers.Serializer[Any]):
    """What the one-click button sends.

    `confirmed` is not a formality and is not defaulted to true: this issues a numbered tax
    document and moves stock, and the only way back is another credit note.
    """

    reason = serializers.CharField(max_length=300)
    confirmed = serializers.BooleanField()
    kind = serializers.ChoiceField(choices=CreditNoteKind.choices, default=CreditNoteKind.RETURN)
    reason_code = serializers.ChoiceField(choices=ReturnReason.choices, default=ReturnReason.OTHER)
    destination = serializers.ChoiceField(
        choices=ReturnDestination.choices, default=ReturnDestination.QUARANTINE
    )
