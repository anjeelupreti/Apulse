"""The catalogue, and the search a counter actually uses.

Two endpoints doing different jobs on purpose. `/catalogue/items/` is the master list: the whole
record, for a management screen. `/catalogue/counter/` is what somebody types into while a
customer waits — fewer fields, stock and price for one branch, and a barcode lookup beside it.

Keeping them apart means the search can stay fast and the detail screen can stay complete, instead
of one endpoint doing both badly.
"""

from typing import Any

from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from core.catalog import permissions as perms
from core.catalog.models import Item
from core.catalog.services import find_by_barcode
from kernel.foundation.api.viewsets import ReadOnlyTenantViewSet
from kernel.tenancy.models import Branch

from .serializers import (
    BarcodeLookupSerializer,
    BarcodeMatchSerializer,
    CounterItemSerializer,
    ItemSerializer,
)


class ItemViewSet(ReadOnlyTenantViewSet):
    """The catalogue as a master list."""

    serializer_class = ItemSerializer
    required_permissions = (perms.ITEM_VIEW.code,)
    #: An item belongs to the account, not to a branch, so there is nothing to scope by.
    branch_field = None
    branch_scope_permission = None
    search_fields = ("code", "name", "name_ne")
    ordering_fields = ("name", "code", "created_at")
    ordering = ("name",)

    def get_queryset(self) -> QuerySet[Item]:
        queryset = Item.objects.select_related(
            "base_unit", "category", "manufacturer", "tax_category"
        ).prefetch_related("units__unit", "barcodes")
        if self.request.query_params.get("include_archived") != "true":
            queryset = queryset.filter(archived_at__isnull=True)
        return queryset


class CounterViewSet(ReadOnlyTenantViewSet):
    """What the person at the till searches.

    A branch is required rather than optional: "is there any" has no answer without one, and
    silently answering for the whole account would tell somebody in Birgunj about stock sitting in
    Kathmandu.
    """

    serializer_class = CounterItemSerializer
    required_permissions = (perms.ITEM_VIEW.code,)
    #: `?branch=` here means "whose shelves", not "which rows" — the view reads it itself.
    branch_field = None
    branch_scope_permission = None
    search_fields = ("code", "name", "name_ne")
    ordering_fields = ("name", "code")
    ordering = ("name",)
    pagination_class = None  # a counter search wants the first few, fast; it pages by typing more

    #: Somebody with a customer waiting reads the first few and types another letter. Returning
    #: four hundred paracetamols would be slower and no more useful.
    limit = 25

    def get_queryset(self) -> QuerySet[Item]:
        queryset = (
            Item.objects.filter(archived_at__isnull=True)
            .select_related("base_unit")
            .prefetch_related("units__unit")
        )
        term = self.request.query_params.get("q", "").strip()
        if term:
            queryset = queryset.filter(
                Q(name__icontains=term)
                | Q(name_ne__icontains=term)
                | Q(code__icontains=term)
                | Q(barcodes__code=term)
            ).distinct()
        return queryset

    def filter_queryset(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        """Limit *after* filtering. A slice cannot be filtered, and the limit is not a filter."""
        return super().filter_queryset(queryset)[: self.limit]

    def get_serializer_context(self) -> dict[str, Any]:
        return {**super().get_serializer_context(), "branch": self._branch()}

    def _branch(self) -> Branch | None:
        branch_id = self.request.query_params.get("branch")
        return get_object_or_404(Branch, pk=branch_id) if branch_id else None

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "q", str, description="Name, code or barcode. Matches Devanagari names too."
            ),
            OpenApiParameter(
                "branch",
                str,
                description="Whose shelves to report stock and price from. Required to see either.",
            ),
        ],
        responses={200: CounterItemSerializer(many=True)},
        description=(
            "The counter's search. Returns at most twenty-five, with the price of the stock "
            "actually on the shelf — the same figure the bill will charge."
        ),
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=BarcodeLookupSerializer,
        responses={200: BarcodeMatchSerializer},
        description=(
            "Look up a scanned barcode. Returns the item **and the pack the barcode was on**, so "
            "scanning a box adds a box rather than a tablet."
        ),
    )
    @action(detail=False, methods=["post"], url_path="barcode")
    def barcode(self, request: Request) -> Response:
        payload = BarcodeLookupSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        item, pack = find_by_barcode(payload.validated_data["code"])
        return Response(
            BarcodeMatchSerializer(
                {"item": item, "unit": pack.unit, "factor": pack.factor},
                context={"branch": self._branch()},
            ).data
        )
