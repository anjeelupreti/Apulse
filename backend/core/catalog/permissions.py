"""Catalogue permissions."""

from kernel.rbac.registry import register

ITEM_VIEW = register("catalog.item.view", "View the catalogue", "सूची हेर्ने", is_read_only=True)
ITEM_MANAGE = register(
    "catalog.item.manage",
    "Add and edit items",
    "वस्तु थप्ने / सम्पादन",
    description="Includes the printed price and the tax category, so it changes what is charged.",
)
ITEM_PRICE = register(
    "catalog.item.price",
    "Change prices",
    "मूल्य परिवर्तन",
    description="Separate from editing an item: a price change is what a customer feels.",
)
