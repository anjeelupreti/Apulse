"""Inventory error codes."""

from shared.errors import register

INSUFFICIENT_STOCK = register(
    "INSUFFICIENT_STOCK",
    409,
    "There is not enough stock available.",
    "पर्याप्त मौज्दात छैन।",
)
EXPIRED_BATCH = register(
    "EXPIRED_BATCH",
    409,
    "This batch has expired and cannot be sold.",
    "यो ब्याचको म्याद सकिएको छ; बिक्री गर्न मिल्दैन।",
)
BATCH_NOT_SELLABLE = register(
    "BATCH_NOT_SELLABLE",
    409,
    "This batch is not available for sale.",
    "यो ब्याच बिक्रीका लागि उपलब्ध छैन।",
)
