"""What the counter needs to see about an item before it can sell one.

Not the whole record. Somebody typing "para" into a search box wants to know: is there any, what
does it cost, and when does the nearest one expire. Everything else is a detail screen.
"""

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from core.catalog.models import Item, ItemBarcode, ItemUnit, UnitOfMeasure


class UnitSerializer(serializers.ModelSerializer[UnitOfMeasure]):
    class Meta:
        model = UnitOfMeasure
        fields = ("id", "code", "name", "name_ne", "name_plural")
        read_only_fields = fields


class ItemUnitSerializer(serializers.ModelSerializer[ItemUnit]):
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    unit_name = serializers.CharField(source="unit.name", read_only=True)

    class Meta:
        model = ItemUnit
        fields = (
            "id",
            "unit",
            "unit_code",
            "unit_name",
            "factor",
            "is_sale_default",
            "is_purchase_default",
        )
        read_only_fields = fields


class BarcodeSerializer(serializers.ModelSerializer[ItemBarcode]):
    unit_code = serializers.CharField(source="item_unit.unit.code", read_only=True, default="")

    class Meta:
        model = ItemBarcode
        fields = ("id", "code", "item_unit", "unit_code", "is_primary")
        read_only_fields = fields


class ItemSerializer(serializers.ModelSerializer[Item]):
    """The full record, for a detail screen."""

    base_unit_code = serializers.CharField(source="base_unit.code", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    manufacturer_name = serializers.CharField(
        source="manufacturer.name", read_only=True, default=""
    )
    tax_percentage = serializers.SerializerMethodField()
    is_archived = serializers.BooleanField(read_only=True)
    packs = ItemUnitSerializer(source="units", many=True, read_only=True)
    barcodes = BarcodeSerializer(many=True, read_only=True)

    class Meta:
        model = Item
        fields = (
            "id",
            "code",
            "name",
            "name_ne",
            "item_type",
            "category",
            "category_name",
            "manufacturer",
            "manufacturer_name",
            "base_unit",
            "base_unit_code",
            "tax_category",
            "tax_percentage",
            "mrp",
            "is_batch_tracked",
            "is_expiry_tracked",
            "allow_loose_sale",
            "archived_at",
            "is_archived",
            "packs",
            "barcodes",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_tax_percentage(self, item: Item) -> str:
        from django.utils import timezone

        return str(item.tax_category.rate_on(timezone.localdate()))


class CounterItemSerializer(serializers.ModelSerializer[Item]):
    """The search result a counter screen shows: can I sell this, and for how much?

    The stock figures are computed per row rather than annotated, which is fine for a page of
    twenty-five and would not be for an export. An export should use a different endpoint rather
    than making this one clever.
    """

    base_unit_code = serializers.CharField(source="base_unit.code", read_only=True)
    sale_unit = serializers.SerializerMethodField()
    available = serializers.SerializerMethodField()
    on_hand = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    nearest_expiry = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = (
            "id",
            "code",
            "name",
            "name_ne",
            "item_type",
            "base_unit",
            "base_unit_code",
            "sale_unit",
            "mrp",
            "price",
            "available",
            "on_hand",
            "nearest_expiry",
            "allow_loose_sale",
            "is_batch_tracked",
        )
        read_only_fields = fields

    @property
    def _branch(self) -> Any:
        return self.context.get("branch")

    def get_sale_unit(self, item: Item) -> dict[str, Any] | None:
        pack = next((unit for unit in item.units.all() if unit.is_sale_default), None)
        if pack is None:
            return None
        return {
            "id": str(pack.unit_id),
            "code": pack.unit.code,
            "name": pack.unit.name,
            "factor": str(pack.factor),
        }

    def get_available(self, item: Item) -> str:
        from core.inventory.services import available_quantity

        if self._branch is None:
            return "0.000"
        return str(available_quantity(item=item, branch=self._branch))

    def get_on_hand(self, item: Item) -> str:
        from core.inventory.services import on_hand_quantity

        if self._branch is None:
            return "0.000"
        return str(on_hand_quantity(item=item, branch=self._branch))

    def get_price(self, item: Item) -> str | None:
        """The printed price of the stock actually on the shelf, nearest expiry first.

        The same rule the bill uses, so the number on the search result is the number that will
        appear on the line — a search that quotes the item's price while the bill charges the
        batch's is a support call waiting to happen.
        """
        batch = self._nearest_batch(item)
        if batch is not None and batch.mrp:
            return str(batch.mrp)
        return str(item.mrp) if item.mrp else None

    def get_nearest_expiry(self, item: Item) -> str | None:
        batch = self._nearest_batch(item)
        return batch.expiry_date.isoformat() if batch and batch.expiry_date else None

    def _nearest_batch(self, item: Item) -> Any:
        from core.inventory.models import StockBalance

        if self._branch is None:
            return None
        balance = (
            StockBalance.objects.filter(item=item, branch=self._branch, quantity__gt=0)
            .select_related("batch")
            .exclude(batch__isnull=True)
            .order_by("batch__expiry_date")
            .first()
        )
        return balance.batch if balance else None


class BarcodeLookupSerializer(serializers.Serializer[Any]):
    code = serializers.CharField(max_length=64)


class BarcodeMatchSerializer(serializers.Serializer[Any]):
    """What a scanner gets back: the item, and the pack the barcode was on.

    Scanning a box should add a box, not a tablet, which is why the unit comes back with it.
    """

    item = CounterItemSerializer()
    unit = UnitSerializer()
    factor = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0"))
