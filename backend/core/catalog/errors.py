"""Catalogue error codes."""

from shared.errors import register

ITEM_BARCODE_UNKNOWN = register(
    "ITEM_BARCODE_UNKNOWN",
    404,
    "No item matches that barcode.",
    "त्यो बारकोडसँग मिल्ने वस्तु फेला परेन।",
)
ITEM_UNIT_UNKNOWN = register(
    "ITEM_UNIT_UNKNOWN",
    400,
    "This item is not sold in that pack.",
    "यो वस्तु त्यो प्याकमा बिक्री हुँदैन।",
)
QUANTITY_NOT_WHOLE = register(
    "QUANTITY_NOT_WHOLE",
    400,
    "This item cannot be split. Enter a whole number.",
    "यो वस्तु टुक्रा गरी बेच्न मिल्दैन। पूरा संख्या राख्नुहोस्।",
)
LOOSE_SALE_NOT_ALLOWED = register(
    "LOOSE_SALE_NOT_ALLOWED",
    400,
    "This item is only sold in full packs.",
    "यो वस्तु पूरा प्याकमा मात्र बिक्री हुन्छ।",
)
