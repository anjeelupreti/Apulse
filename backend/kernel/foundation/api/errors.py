"""Error codes the API layer itself raises, as opposed to any one domain."""

from shared.errors import codes, register

IDEMPOTENCY_KEY_REQUIRED = register(
    "IDEMPOTENCY_KEY_REQUIRED",
    400,
    "This request needs an Idempotency-Key header so a retry cannot repeat it.",
    "यो अनुरोधमा Idempotency-Key हेडर आवश्यक छ, जसले दोहोरो प्रविष्टि रोक्छ।",
)
IDEMPOTENT_REQUEST_IN_FLIGHT = register(
    "IDEMPOTENT_REQUEST_IN_FLIGHT",
    409,
    "The same request is still being processed. Wait for it to finish before retrying.",
    "यही अनुरोध अझै प्रशोधन हुँदैछ। सकिने कुर्नुहोस्, त्यसपछि मात्र पुनः प्रयास गर्नुहोस्।",
)
IDEMPOTENCY_KEY_REUSED = register(
    "IDEMPOTENCY_KEY_REUSED",
    409,
    "That idempotency key was already used for a different request.",
    "त्यो idempotency key फरक अनुरोधका लागि पहिले नै प्रयोग भइसकेको छ।",
)
VERSION_REQUIRED = register(
    "VERSION_REQUIRED",
    400,
    "Send the version you are editing, so a change made by somebody else is not overwritten.",
    "तपाईंले सम्पादन गरिरहेको संस्करण पठाउनुहोस्, अन्यथा अर्कोले गरेको परिवर्तन मेटिन सक्छ।",
)
#: Already in the platform catalogue — re-exported so callers here have one place to look.
VERSION_CONFLICT = codes.VERSION_CONFLICT
