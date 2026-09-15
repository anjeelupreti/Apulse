"""Tenancy error codes, registered into the platform-wide catalogue."""

from shared.errors import register

TENANT_NOT_FOUND = register(
    "TENANT_NOT_FOUND",
    404,
    "No pharmacy account exists at this address.",
    "यो ठेगानामा कुनै खाता फेला परेन।",
)
TENANT_INACTIVE = register(
    "TENANT_INACTIVE",
    403,
    "This account is not active. Please contact support.",
    "यो खाता सक्रिय छैन। कृपया सहयोग केन्द्रमा सम्पर्क गर्नुहोस्।",
)
TENANT_READ_ONLY = register(
    "TENANT_READ_ONLY",
    403,
    "This account is read-only. Records can still be viewed, printed and exported.",
    "यो खाता हाल पढ्न मात्र मिल्ने अवस्थामा छ। रेकर्ड हेर्न, छाप्न र निर्यात गर्न भने सकिन्छ।",
)
