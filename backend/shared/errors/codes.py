"""Platform-wide generic error codes. Modules register their own codes with a module prefix."""

from .catalogue import register

VALIDATION_ERROR = register("VALIDATION_ERROR", 400, "Invalid input.", "पेश गरिएको विवरण मान्य छैन।")
MALFORMED_REQUEST = register("MALFORMED_REQUEST", 400, "Malformed request.", "अनुरोधको ढाँचा मिलेन।")
AUTH_NOT_AUTHENTICATED = register(
    "AUTH_NOT_AUTHENTICATED", 401, "Authentication required.", "कृपया लगइन गर्नुहोस्।"
)
AUTH_FAILED = register("AUTH_FAILED", 401, "Invalid credentials.", "लगइन विवरण मिलेन।")
PERMISSION_DENIED = register(
    "PERMISSION_DENIED",
    403,
    "You do not have permission to perform this action.",
    "तपाईंलाई यो कार्य गर्ने अनुमति छैन।",
)
NOT_FOUND = register("NOT_FOUND", 404, "Not found.", "फेला परेन।")
METHOD_NOT_ALLOWED = register("METHOD_NOT_ALLOWED", 405, "Method not allowed.", "यो विधि अनुमति छैन।")
NOT_ACCEPTABLE = register(
    "NOT_ACCEPTABLE",
    406,
    "Requested response format is not available.",
    "माग गरिएको ढाँचामा जवाफ उपलब्ध छैन।",
)
VERSION_CONFLICT = register(
    "VERSION_CONFLICT",
    409,
    "This record was changed by someone else. Reload and try again.",
    "यो रेकर्ड अरू कसैले परिवर्तन गरिसकेको छ। पुनः लोड गरेर फेरि प्रयास गर्नुहोस्।",
)
UNSUPPORTED_MEDIA_TYPE = register(
    "UNSUPPORTED_MEDIA_TYPE", 415, "Unsupported content type.", "यो सामग्री प्रकार समर्थित छैन।"
)
RATE_LIMITED = register(
    "RATE_LIMITED",
    429,
    "Too many requests. Please try again later.",
    "धेरै अनुरोध भयो। केही समयपछि फेरि प्रयास गर्नुहोस्।",
)
SERVER_ERROR = register(
    "SERVER_ERROR",
    500,
    "An unexpected error occurred.",
    "अप्रत्याशित त्रुटि भयो।",
)
