"""Payment and till permissions."""

from kernel.rbac.registry import register

PAYMENT_TAKE = register("payments.payment.take", "Take payments", "भुक्तानी लिने", is_read_only=False)
PAYMENT_REFUND = register("payments.payment.refund", "Give refunds", "रकम फिर्ता दिने")
PAYMENT_REVERSE = register(
    "payments.payment.reverse",
    "Reverse a payment",
    "भुक्तानी उल्टाउने",
    description="Records the opposite movement. The original payment is never edited.",
)

CREDIT_SELL = register("payments.credit.sell", "Sell on account", "उधारोमा बिक्री गर्ने")
CREDIT_OVERRIDE = register(
    "payments.credit.override",
    "Override a credit limit or an overdue block",
    "उधारो सीमा वा म्याद नाघेको रोक हटाउने",
    description=(
        "Lets a sale go on account past the customer's limit, or while they have bills overdue. "
        "Every override is recorded with its reason and who gave it."
    ),
)

SHIFT_OPEN = register("payments.shift.open", "Open a till", "गल्ला खोल्ने")
SHIFT_CLOSE = register("payments.shift.close", "Close and count a till", "गल्ला बन्द तथा गणना")
SHIFT_APPROVE = register(
    "payments.shift.approve",
    "Sign off a counted till",
    "गणना भएको गल्ला प्रमाणित गर्ने",
    description="A cashier cannot sign off their own count; this belongs to a supervisor.",
)
SHIFT_VIEW = register(
    "payments.shift.view", "View tills and their counts", "गल्ला हेर्ने", is_read_only=True
)
PAYMENT_VIEW = register("payments.payment.view", "View payments", "भुक्तानी हेर्ने", is_read_only=True)
LEDGER_VIEW = register(
    "payments.ledger.view",
    "View customer statements and ageing",
    "ग्राहक खाता तथा बाँकी हेर्ने",
    is_read_only=True,
)
