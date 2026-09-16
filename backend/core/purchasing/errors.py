"""Purchasing error codes."""

from shared.errors import register

RECEIPT_NOT_EDITABLE = register(
    "RECEIPT_NOT_EDITABLE",
    409,
    "This goods receipt has been posted and can no longer be changed.",
    "यो सामान प्राप्ति दर्ता भइसकेको छ; अब परिवर्तन गर्न मिल्दैन।",
)
RECEIPT_HAS_NO_LINES = register(
    "RECEIPT_HAS_NO_LINES",
    400,
    "Add at least one item before posting.",
    "दर्ता गर्नुअघि कम्तीमा एउटा वस्तु थप्नुहोस्।",
)
BATCH_DETAILS_REQUIRED = register(
    "BATCH_DETAILS_REQUIRED",
    400,
    "This item needs a batch number and an expiry date.",
    "यो वस्तुका लागि ब्याच नम्बर र म्याद सकिने मिति चाहिन्छ।",
)
RECEIVING_EXPIRED_STOCK = register(
    "RECEIVING_EXPIRED_STOCK",
    400,
    "This batch has already expired. Confirm deliberately if it is being taken in to return.",
    "यो ब्याचको म्याद सकिसकेको छ। फिर्ता पठाउनका लागि मात्र भए पुष्टि गर्नुहोस्।",
)
SUPPLIER_INVOICE_ALREADY_ENTERED = register(
    "SUPPLIER_INVOICE_ALREADY_ENTERED",
    409,
    "This supplier invoice has already been entered.",
    "यो आपूर्तिकर्ताको बिल पहिले नै दर्ता भइसकेको छ।",
)
