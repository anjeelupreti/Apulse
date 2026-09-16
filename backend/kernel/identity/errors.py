"""Authentication error codes.

Every failure a signed-out caller can trigger returns the same generic code, so the API never
reveals whether an email address or phone number belongs to an account.
"""

from shared.errors import register

AUTH_TOO_MANY_ATTEMPTS = register(
    "AUTH_TOO_MANY_ATTEMPTS",
    429,
    "Too many sign-in attempts. Please wait and try again.",
    "धेरै पटक प्रयास भयो। केही समयपछि फेरि प्रयास गर्नुहोस्।",
)
AUTH_ACCOUNT_DISABLED = register(
    "AUTH_ACCOUNT_DISABLED",
    403,
    "This account has been disabled. Please contact your pharmacy administrator.",
    "यो खाता निष्क्रिय गरिएको छ। कृपया आफ्नो फार्मेसी प्रशासकलाई सम्पर्क गर्नुहोस्।",
)
AUTH_NO_TENANT_ACCESS = register(
    "AUTH_NO_TENANT_ACCESS",
    403,
    "You do not have access to this pharmacy account.",
    "तपाईंलाई यो फार्मेसी खातामा पहुँच छैन।",
)
AUTH_CHALLENGE_INVALID = register(
    "AUTH_CHALLENGE_INVALID",
    401,
    "This sign-in attempt has expired. Please start again.",
    "यो प्रयासको समय सकियो। कृपया फेरि सुरु गर्नुहोस्।",
)
AUTH_TWO_FACTOR_INVALID = register(
    "AUTH_TWO_FACTOR_INVALID",
    401,
    "That verification code is not valid.",
    "प्रमाणीकरण कोड मिलेन।",
)
AUTH_TWO_FACTOR_ALREADY_ENABLED = register(
    "AUTH_TWO_FACTOR_ALREADY_ENABLED",
    409,
    "Two-factor authentication is already enabled.",
    "दुई-चरण प्रमाणीकरण पहिले नै सक्रिय छ।",
)
AUTH_TWO_FACTOR_NOT_SET_UP = register(
    "AUTH_TWO_FACTOR_NOT_SET_UP",
    409,
    "Start two-factor setup before confirming a code.",
    "कोड पुष्टि गर्नुअघि दुई-चरण प्रमाणीकरण सुरु गर्नुहोस्।",
)
