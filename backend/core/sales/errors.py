"""Sales error codes."""

from shared.errors import register

INVOICE_NOT_EDITABLE = register(
    "INVOICE_NOT_EDITABLE",
    409,
    "This invoice has been issued and can no longer be changed.",
    "यो बीजक जारी भइसकेको छ; अब परिवर्तन गर्न मिल्दैन।",
)
INVOICE_HAS_NO_LINES = register(
    "INVOICE_HAS_NO_LINES",
    400,
    "Add at least one item before issuing the invoice.",
    "बीजक जारी गर्नुअघि कम्तीमा एउटा वस्तु थप्नुहोस्।",
)
PRICE_ABOVE_MRP = register(
    "PRICE_ABOVE_MRP",
    400,
    "The price is above the maximum retail price printed on the pack.",
    "मूल्य प्याकमा छापिएको अधिकतम खुद्रा मूल्यभन्दा बढी छ।",
)
NO_PRICE_SET = register(
    "NO_PRICE_SET",
    400,
    "This item has no price. Enter one, or record the printed price on the batch.",
    "यो वस्तुको मूल्य तोकिएको छैन। मूल्य राख्नुहोस् वा ब्याचमा छापिएको मूल्य दर्ता गर्नुहोस्।",
)
