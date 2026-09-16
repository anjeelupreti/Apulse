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
CREDIT_NOTE_NEEDS_AN_ISSUED_INVOICE = register(
    "CREDIT_NOTE_NEEDS_AN_ISSUED_INVOICE",
    400,
    "A credit note can only be raised against an invoice that has been issued.",
    "जारी भइसकेको बीजकविरुद्ध मात्र क्रेडिट नोट काट्न मिल्छ।",
)
CREDIT_NOTE_NEEDS_A_REASON = register(
    "CREDIT_NOTE_NEEDS_A_REASON",
    400,
    "Say why this credit note is being raised.",
    "यो क्रेडिट नोट किन काटिँदै छ, कारण उल्लेख गर्नुहोस्।",
)
CREDIT_NOTE_NOT_EDITABLE = register(
    "CREDIT_NOTE_NOT_EDITABLE",
    409,
    "This credit note has been issued and can no longer be changed.",
    "यो क्रेडिट नोट जारी भइसकेको छ; अब परिवर्तन गर्न मिल्दैन।",
)
CREDIT_NOTE_HAS_NO_LINES = register(
    "CREDIT_NOTE_HAS_NO_LINES",
    400,
    "Add at least one line before issuing the credit note.",
    "क्रेडिट नोट जारी गर्नुअघि कम्तीमा एउटा पङ्क्ति थप्नुहोस्।",
)
CREDIT_LINE_IS_NOT_ON_THIS_INVOICE = register(
    "CREDIT_LINE_IS_NOT_ON_THIS_INVOICE",
    400,
    "That line is not on the invoice being credited.",
    "त्यो पङ्क्ति क्रेडिट गरिँदै गरेको बीजकमा छैन।",
)
CREDIT_QUANTITY_MUST_BE_POSITIVE = register(
    "CREDIT_QUANTITY_MUST_BE_POSITIVE",
    400,
    "Enter how much is being returned.",
    "कति फिर्ता हुँदै छ सो परिमाण राख्नुहोस्।",
)
CREDIT_EXCEEDS_WHAT_WAS_SOLD = register(
    "CREDIT_EXCEEDS_WHAT_WAS_SOLD",
    400,
    "More is being returned than was sold on this bill.",
    "यो बीजकमा बेचिएको भन्दा बढी फिर्ता गर्न खोजिँदै छ।",
)
NO_QUARANTINE_LOCATION = register(
    "NO_QUARANTINE_LOCATION",
    409,
    "This branch has nowhere to quarantine returned stock. Set up a quarantine location first.",
    "यस शाखामा फिर्ता सामान राख्ने क्वारेन्टाइन स्थान छैन। पहिले सो स्थान बनाउनुहोस्।",
)
INVOICE_ALREADY_PARTLY_CREDITED = register(
    "INVOICE_ALREADY_PARTLY_CREDITED",
    409,
    "Part of this bill has already been credited. Credit the rest instead of cancelling it.",
    "यो बीजकको केही अंश पहिले नै क्रेडिट भइसकेको छ। रद्द गर्नुको सट्टा बाँकी अंश क्रेडिट गर्नुहोस्।",
)
