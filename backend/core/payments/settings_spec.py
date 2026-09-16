"""Settings the payments and credit code reads."""

from decimal import Decimal

from kernel.settings.registry import Scope, SettingKind, define

CREDIT_OVER_LIMIT = define(
    "payments.over_limit_behaviour",
    SettingKind.CHOICE,
    "block",
    "When a sale would exceed the credit limit",
    "उधारो सीमा नाघ्ने अवस्थामा",
    choices=("block", "warn"),
    description=(
        "Block refuses the sale unless somebody with authority overrides it. Warn lets it "
        "through and records the fact. A shop that sells to two hospitals on 60-day terms may "
        "reasonably choose warn; one selling to walk-in families should not."
    ),
    is_sensitive=True,
)

CREDIT_OVERDUE = define(
    "payments.overdue_behaviour",
    SettingKind.CHOICE,
    "block",
    "When a customer has bills past their due date",
    "ग्राहकका म्याद नाघेका बीजक हुँदा",
    choices=("block", "warn"),
    description="Separate from the limit, because not paying at all is the worse signal.",
    is_sensitive=True,
)

OVERDUE_GRACE_DAYS = define(
    "payments.overdue_grace_days",
    SettingKind.INTEGER,
    0,
    "Days of grace before a bill counts as overdue",
    "बीजक म्याद नाघेको मानिनुअघि दिने छुटका दिन",
    minimum=0,
    maximum=90,
    description=(
        "A customer who pays on the 31st of a 30-day arrangement is not a credit risk, and "
        "blocking them at the counter over one day costs more than it saves."
    ),
)

VARIANCE_TOLERANCE = define(
    "payments.till_variance_tolerance",
    SettingKind.DECIMAL,
    Decimal("1.00"),
    "Till difference that closes without an explanation",
    "स्पष्टीकरणविना गल्ला बन्द हुने फरक रकम",
    minimum=Decimal("0"),
    maximum=Decimal("100"),
    description=(
        "A rupee either way on a day of cash handling is a rounding artefact. Demanding a "
        "paragraph for it only teaches people to type 'ok' into the box."
    ),
)

REQUIRE_WITNESS_FOR_CASH_OUT = define(
    "payments.require_witness_for_cash_out",
    SettingKind.BOOLEAN,
    True,
    "Cash taken out of the till must be witnessed",
    "गल्लाबाट नगद निकाल्दा साक्षी अनिवार्य",
    description="One person alone deciding money left the till is not a control.",
    is_sensitive=True,
)

OPENING_FLOAT = define(
    "payments.default_opening_float",
    SettingKind.DECIMAL,
    Decimal("0"),
    "Float a till opens with by default",
    "गल्ला खुल्दाको सुरु रकम",
    minimum=Decimal("0"),
    scopes=(Scope.PLATFORM, Scope.TENANT, Scope.LEGAL_ENTITY, Scope.BRANCH),
)
