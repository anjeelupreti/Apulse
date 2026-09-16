"""Payment and shift error codes, worded for the person at the till."""

from shared.errors import register

NO_OPEN_SHIFT = register(
    "NO_OPEN_SHIFT",
    409,
    "Open the till before taking any money.",
    "पैसा लिनुअघि गल्ला खोल्नुहोस्।",
)
SHIFT_ALREADY_OPEN = register(
    "SHIFT_ALREADY_OPEN",
    409,
    "This counter already has an open till. Close it before opening another.",
    "यो काउन्टरमा पहिले नै गल्ला खुला छ। अर्को खोल्नुअघि बन्द गर्नुहोस्।",
)
SHIFT_ALREADY_CLOSED = register(
    "SHIFT_ALREADY_CLOSED",
    409,
    "This till has already been closed.",
    "यो गल्ला पहिले नै बन्द भइसकेको छ।",
)
PAYMENT_MUST_BE_POSITIVE = register(
    "PAYMENT_MUST_BE_POSITIVE",
    400,
    "Enter an amount greater than zero.",
    "शून्यभन्दा बढी रकम राख्नुहोस्।",
)
PAYMENT_EXCEEDS_WHAT_IS_DUE = register(
    "PAYMENT_EXCEEDS_WHAT_IS_DUE",
    400,
    "That is more than is outstanding on this bill.",
    "यो बीजकमा बाँकी रहेको भन्दा बढी रकम हो।",
)
NOT_ENOUGH_TENDERED = register(
    "NOT_ENOUGH_TENDERED",
    400,
    "The cash handed over is less than the amount being paid.",
    "दिइएको नगद भुक्तानी रकमभन्दा कम छ।",
)
CHANGE_ONLY_FROM_CASH = register(
    "CHANGE_ONLY_FROM_CASH",
    400,
    "Change can only be given from cash.",
    "फिर्ता रकम नगदबाट मात्र दिन मिल्छ।",
)
REFERENCE_REQUIRED = register(
    "REFERENCE_REQUIRED",
    400,
    "This payment method needs its transaction reference recorded.",
    "यो भुक्तानी माध्यमको कारोबार सन्दर्भ नम्बर राख्नुपर्छ।",
)
CASH_OUT_NEEDS_A_WITNESS = register(
    "CASH_OUT_NEEDS_A_WITNESS",
    400,
    "Taking cash out of the drawer must be witnessed. Record the witness's name.",
    "गल्लाबाट नगद निकाल्दा साक्षी चाहिन्छ। साक्षीको नाम राख्नुहोस्।",
)
CASH_MOVEMENT_NEEDS_A_REASON = register(
    "CASH_MOVEMENT_NEEDS_A_REASON",
    400,
    "Say what this cash was for.",
    "यो नगद केका लागि हो, कारण उल्लेख गर्नुहोस्।",
)
VARIANCE_NEEDS_AN_EXPLANATION = register(
    "VARIANCE_NEEDS_AN_EXPLANATION",
    400,
    "The drawer does not match the register. Explain the difference before closing.",
    "गल्लाको रकम हिसाबसँग मिलेन। बन्द गर्नुअघि फरकको कारण लेख्नुहोस्।",
)
UNKNOWN_DENOMINATION = register(
    "UNKNOWN_DENOMINATION",
    400,
    "That is not a Nepali note or coin.",
    "यो नेपाली नोट वा सिक्का होइन।",
)
PAYMENT_ALREADY_REVERSED = register(
    "PAYMENT_ALREADY_REVERSED",
    409,
    "This payment has already been reversed.",
    "यो भुक्तानी पहिले नै उल्टाइसकिएको छ।",
)
CREDIT_NEEDS_A_NAMED_CUSTOMER = register(
    "CREDIT_NEEDS_A_NAMED_CUSTOMER",
    400,
    "A sale on account needs a customer account. Select or add the customer first.",
    "उधारो बिक्रीका लागि ग्राहकको खाता चाहिन्छ। पहिले ग्राहक छान्नुहोस् वा थप्नुहोस्।",
)
CREDIT_LIMIT_EXCEEDED = register(
    "CREDIT_LIMIT_EXCEEDED",
    409,
    "This would take the customer past their credit limit.",
    "यसले ग्राहकको उधारो सीमा नाघ्छ।",
)
CUSTOMER_HAS_OVERDUE_BILLS = register(
    "CUSTOMER_HAS_OVERDUE_BILLS",
    409,
    "This customer has bills past their due date. Settle those before selling on account again.",
    "यो ग्राहकका म्याद नाघेका बीजक छन्। पुनः उधारो दिनुअघि ती चुक्ता गर्नुहोस्।",
)
OVERRIDE_NEEDS_A_NAME = register(
    "OVERRIDE_NEEDS_A_NAME",
    400,
    "An override has to say who authorised it.",
    "छुट कसले स्वीकृत गर्‍यो सो उल्लेख गर्नुपर्छ।",
)
