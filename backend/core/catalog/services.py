"""Building the catalogue, and converting between packs and base units."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

import structlog
from django.db import transaction

from kernel.audit import services as audit
from shared.errors import DomainError

from . import errors
from .models import (
    FACTOR_DECIMALS,
    QUANTITY_DECIMALS,
    Item,
    ItemBarcode,
    ItemUnit,
    UnitOfMeasure,
)

logger = structlog.get_logger(__name__)

_QUANTITY_STEP = Decimal(1).scaleb(-QUANTITY_DECIMALS)

#: The units a pharmacy actually uses. Shared by every account, because a tablet is a tablet.
SEED_UNITS: tuple[dict[str, Any], ...] = (
    {"code": "pcs", "name": "Piece", "plural": "Pieces", "name_ne": "थान"},
    {"code": "tab", "name": "Tablet", "plural": "Tablets", "name_ne": "ट्याब्लेट"},
    {"code": "cap", "name": "Capsule", "plural": "Capsules", "name_ne": "क्याप्सुल"},
    {
        "code": "ml",
        "name": "Millilitre",
        "plural": "Millilitres",
        "name_ne": "मिलिलिटर",
        "allows_fractions": True,
    },
    {
        "code": "gm",
        "name": "Gram",
        "plural": "Grams",
        "name_ne": "ग्राम",
        "allows_fractions": True,
    },
    {"code": "strip", "name": "Strip", "plural": "Strips", "name_ne": "स्ट्रिप"},
    {"code": "box", "name": "Box", "plural": "Boxes", "name_ne": "बाकस"},
    {"code": "bottle", "name": "Bottle", "plural": "Bottles", "name_ne": "बोतल"},
    {"code": "tube", "name": "Tube", "plural": "Tubes", "name_ne": "ट्युब"},
    {"code": "vial", "name": "Vial", "plural": "Vials", "name_ne": "भायल"},
    {"code": "ampoule", "name": "Ampoule", "plural": "Ampoules", "name_ne": "एम्पुल"},
    {"code": "sachet", "name": "Sachet", "plural": "Sachets", "name_ne": "सस्केट"},
    {"code": "packet", "name": "Packet", "plural": "Packets", "name_ne": "प्याकेट"},
    {"code": "carton", "name": "Carton", "plural": "Cartons", "name_ne": "कार्टन"},
)


@transaction.atomic
def sync_units() -> int:
    for seed in SEED_UNITS:
        UnitOfMeasure.objects.update_or_create(
            code=seed["code"],
            defaults={
                "name": seed["name"],
                "name_plural": seed["plural"],
                "name_ne": seed.get("name_ne", ""),
                "allows_fractions": seed.get("allows_fractions", False),
            },
        )
    return len(SEED_UNITS)


def quantize_quantity(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_QUANTITY_STEP, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- building
@transaction.atomic
def create_item(
    *,
    code: str,
    name: str,
    base_unit: UnitOfMeasure,
    tax_category: Any,
    actor: Any = None,
    **fields: Any,
) -> Item:
    """Create an item and its base pack.

    Every item gets a pack of factor 1 for its base unit, so "one tablet" is expressible without
    a special case anywhere else.
    """
    item = cast(
        "Item",
        Item.objects.create(
            code=code, name=name, base_unit=base_unit, tax_category=tax_category, **fields
        ),
    )
    ItemUnit.objects.create(item=item, unit=base_unit, factor=Decimal(1), is_sale_default=True)
    audit.record_create(item, actor=actor)
    return item


@transaction.atomic
def add_pack(
    item: Item,
    unit: UnitOfMeasure,
    factor: Decimal | int | str,
    *,
    is_purchase_default: bool = False,
    is_sale_default: bool = False,
) -> ItemUnit:
    """Add a larger pack, such as a strip of ten or a box of a hundred."""
    factor = Decimal(str(factor)).quantize(Decimal(1).scaleb(-FACTOR_DECIMALS))
    if factor <= 0:
        raise ValueError("A pack must hold more than zero base units.")

    if is_purchase_default:
        ItemUnit.objects.filter(item=item, is_purchase_default=True).update(
            is_purchase_default=False
        )
    if is_sale_default:
        ItemUnit.objects.filter(item=item, is_sale_default=True).update(is_sale_default=False)

    return cast(
        "ItemUnit",
        ItemUnit.objects.create(
            item=item,
            unit=unit,
            factor=factor,
            is_purchase_default=is_purchase_default,
            is_sale_default=is_sale_default,
        ),
    )


def add_barcode(
    item: Item, code: str, *, item_unit: ItemUnit | None = None, is_primary: bool = False
) -> ItemBarcode:
    return cast(
        "ItemBarcode",
        ItemBarcode.objects.create(
            item=item, item_unit=item_unit, code=code.strip(), is_primary=is_primary
        ),
    )


# --------------------------------------------------------------------------- conversion
def unit_for(item: Item, unit: UnitOfMeasure) -> ItemUnit:
    pack = ItemUnit.objects.filter(item=item, unit=unit).first()
    if pack is None:
        raise DomainError(
            errors.ITEM_UNIT_UNKNOWN,
            f"{item.name} is not sold in {unit.label_for(2)}.",
        )
    return cast("ItemUnit", pack)


def to_base(item: Item, quantity: Decimal | int | str, unit: UnitOfMeasure) -> Decimal:
    """Turn a pack quantity into base units. Three boxes of a hundred is three hundred tablets."""
    pack = unit_for(item, unit)
    return quantize_quantity(Decimal(str(quantity)) * pack.factor)


def from_base(item: Item, base_quantity: Decimal | int | str, unit: UnitOfMeasure) -> Decimal:
    """Turn base units into a pack quantity. May be fractional: 15 tablets is 1.5 strips."""
    pack = unit_for(item, unit)
    return quantize_quantity(Decimal(str(base_quantity)) / pack.factor)


def _count_of(quantity: Decimal | int, unit: UnitOfMeasure) -> str:
    value = Decimal(str(quantity))
    rendered = str(int(value)) if value == value.to_integral_value() else str(value.normalize())
    return f"{rendered} {unit.label_for(value)}"


def describe_quantity(item: Item, base_quantity: Decimal | int | str) -> str:
    """Read a quantity the way a storekeeper would: `2 boxes 3 strips 4 tablets`.

    "247 tablets" is correct but means nothing on a shelf. The breakdown is what someone counts.
    """
    remaining = quantize_quantity(Decimal(str(base_quantity)))
    negative = remaining < 0
    remaining = abs(remaining)

    parts: list[str] = []
    packs = (
        ItemUnit.objects.filter(item=item, factor__gt=1).select_related("unit").order_by("-factor")
    )
    for pack in packs:
        whole = int(remaining // pack.factor)
        if whole:
            parts.append(_count_of(whole, pack.unit))
            remaining -= whole * pack.factor

    if remaining > 0 or not parts:
        parts.append(_count_of(remaining, item.base_unit))

    description = " ".join(parts)
    return f"-{description}" if negative else description


# --------------------------------------------------------------------------- validation
def validate_quantity(
    item: Item, base_quantity: Decimal, *, unit: UnitOfMeasure | None = None
) -> None:
    """Refuse a quantity the item cannot actually be handed over in."""
    quantity = quantize_quantity(base_quantity)
    if quantity <= 0:
        raise DomainError(errors.QUANTITY_NOT_WHOLE, "Enter a quantity greater than zero.")

    measured_in = unit or item.base_unit
    if not measured_in.allows_fractions and quantity != quantity.to_integral_value():
        raise DomainError(
            errors.QUANTITY_NOT_WHOLE,
            f"{item.name} is counted in whole {item.base_unit.name.lower()}s.",
        )

    if not item.allow_loose_sale:
        sale_pack = ItemUnit.objects.filter(item=item, is_sale_default=True).first()
        if sale_pack and sale_pack.factor > 1 and quantity % sale_pack.factor != 0:
            raise DomainError(
                errors.LOOSE_SALE_NOT_ALLOWED,
                f"{item.name} is sold in whole {sale_pack.unit.name.lower()}s "
                f"of {int(sale_pack.factor)}.",
            )


# --------------------------------------------------------------------------- lookup
def find_by_barcode(code: str) -> tuple[Item, ItemUnit]:
    """The item a scan refers to, and the pack that was scanned.

    Scanning a box must add a box, not one tablet, so the pack matters as much as the item.
    """
    barcode = (
        ItemBarcode.objects.filter(code=code.strip())
        .select_related("item", "item_unit", "item__base_unit")
        .first()
    )
    if barcode is None:
        raise DomainError(errors.ITEM_BARCODE_UNKNOWN)

    pack = barcode.item_unit
    if pack is None:
        pack = ItemUnit.objects.filter(item=barcode.item, factor=1).first()
    if pack is None:
        raise DomainError(errors.ITEM_UNIT_UNKNOWN, f"{barcode.item.name} has no base pack.")
    return barcode.item, pack
