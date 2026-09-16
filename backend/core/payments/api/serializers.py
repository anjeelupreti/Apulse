"""Money and the till, over the wire."""

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from core.payments.models import (
    CashierShift,
    CashMovement,
    CashMovementKind,
    Payment,
    PaymentMode,
)


class PaymentModeSerializer(serializers.ModelSerializer[PaymentMode]):
    class Meta:
        model = PaymentMode
        fields = (
            "id",
            "code",
            "name",
            "name_ne",
            "kind",
            "requires_reference",
            "gives_change",
            "is_active",
            "sort_order",
        )
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer[Payment]):
    mode_code = serializers.CharField(source="mode.code", read_only=True)
    mode_name = serializers.CharField(source="mode.name", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "direction",
            "mode",
            "mode_code",
            "mode_name",
            "amount",
            "tendered_amount",
            "change_amount",
            "reference",
            "document_type",
            "document_id",
            "document_number",
            "party",
            "received_on",
            "reason",
            "note",
            "created_at",
        )
        read_only_fields = fields


class TenderSerializer(serializers.Serializer[Any]):
    mode = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    reference = serializers.CharField(required=False, allow_blank=True, max_length=120)


class SettleInvoiceSerializer(serializers.Serializer[Any]):
    """Split tender is the normal case, so the payload is a list even for one method."""

    tenders = TenderSerializer(many=True, allow_empty=False)
    shift = serializers.UUIDField(required=False, allow_null=True)
    tendered_cash = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="What the customer actually handed over, when it is more than the bill.",
    )
    override_reason = serializers.CharField(required=False, allow_blank=True, max_length=300)


class RefundSerializer(serializers.Serializer[Any]):
    mode = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )
    shift = serializers.UUIDField(required=False, allow_null=True)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=120)


class ReceiveAgainstSerializer(serializers.Serializer[Any]):
    mode = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    shift = serializers.UUIDField(required=False, allow_null=True)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=120)
    received_on = serializers.DateField(required=False)


# --------------------------------------------------------------------------- the till
class CashMovementSerializer(serializers.ModelSerializer[CashMovement]):
    class Meta:
        model = CashMovement
        fields = ("id", "kind", "amount", "reason", "reference", "witness_name", "created_at")
        read_only_fields = fields


class ShiftSerializer(serializers.ModelSerializer[CashierShift]):
    cashier_name = serializers.CharField(source="cashier.full_name", read_only=True)
    cash_movements = CashMovementSerializer(many=True, read_only=True)
    is_short = serializers.BooleanField(read_only=True)

    class Meta:
        model = CashierShift
        fields = (
            "id",
            "branch",
            "location",
            "cashier",
            "cashier_name",
            "status",
            "business_date",
            "opened_at",
            "closed_at",
            "opening_float",
            "expected_cash",
            "counted_cash",
            "variance",
            "is_short",
            "variance_reason",
            "closed_by",
            "approved_by",
            "approved_at",
            "note",
            "cash_movements",
        )
        read_only_fields = fields


class OpenShiftSerializer(serializers.Serializer[Any]):
    branch = serializers.UUIDField()
    location = serializers.UUIDField()
    opening_float = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="Left out, the branch's usual float is used.",
    )
    business_date = serializers.DateField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)


class DenominationCountSerializer(serializers.Serializer[Any]):
    value = serializers.IntegerField(min_value=1)
    count = serializers.IntegerField(min_value=0)


class CloseShiftSerializer(serializers.Serializer[Any]):
    counts = DenominationCountSerializer(many=True, allow_empty=True)
    variance_reason = serializers.CharField(required=False, allow_blank=True, max_length=300)
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)

    def as_mapping(self) -> dict[int, int]:
        return {row["value"]: row["count"] for row in self.validated_data["counts"]}


class CashMovementInputSerializer(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(choices=CashMovementKind.choices)
    amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        help_text="Positive into the drawer, negative out of it.",
    )
    reason = serializers.CharField(max_length=300)
    witness_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=120)


class ShiftSummarySerializer(serializers.Serializer[Any]):
    """What the Z-report prints and the close is checked against."""

    opening_float = serializers.DecimalField(max_digits=18, decimal_places=2)
    cash_received = serializers.DecimalField(max_digits=18, decimal_places=2)
    cash_refunded = serializers.DecimalField(max_digits=18, decimal_places=2)
    cash_movements = serializers.DecimalField(max_digits=18, decimal_places=2)
    expected_cash = serializers.DecimalField(max_digits=18, decimal_places=2)
    by_mode = serializers.DictField(child=serializers.DecimalField(max_digits=18, decimal_places=2))
    payment_count = serializers.IntegerField()


class CreditDecisionSerializer(serializers.Serializer[Any]):
    """The customer's credit position, so the counter can talk rather than just refuse."""

    allowed = serializers.BooleanField()
    is_warning = serializers.BooleanField()
    limit = serializers.DecimalField(max_digits=18, decimal_places=2)
    exposure = serializers.DecimalField(max_digits=18, decimal_places=2)
    requested = serializers.DecimalField(max_digits=18, decimal_places=2)
    headroom = serializers.DecimalField(max_digits=18, decimal_places=2)
    would_exceed_by = serializers.DecimalField(max_digits=18, decimal_places=2)
    overdue_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    oldest_overdue_days = serializers.IntegerField()
    reason = serializers.CharField(allow_blank=True)


class StatementLineSerializer(serializers.Serializer[Any]):
    on_date = serializers.DateField()
    kind = serializers.CharField()
    reference = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    debit = serializers.DecimalField(max_digits=18, decimal_places=2)
    credit = serializers.DecimalField(max_digits=18, decimal_places=2)
    balance = serializers.DecimalField(max_digits=18, decimal_places=2)
