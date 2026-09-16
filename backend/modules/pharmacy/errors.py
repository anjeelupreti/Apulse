"""Pharmacy error codes.

Worded for the person at the counter, who has a customer waiting and needs to know what to do
next rather than what rule was broken.
"""

from shared.errors import register

PRESCRIPTION_REQUIRED = register(
    "PRESCRIPTION_REQUIRED",
    400,
    "This medicine needs a doctor's prescription. Record the prescription to continue.",
    "यो औषधिका लागि चिकित्सकको प्रेस्क्रिप्सन चाहिन्छ। प्रेस्क्रिप्सन दर्ता गरेर अघि बढ्नुहोस्।",
)
PRESCRIPTION_EXPIRED = register(
    "PRESCRIPTION_EXPIRED",
    400,
    "This prescription is no longer valid. A fresh one is needed.",
    "यो प्रेस्क्रिप्सन मान्य छैन। नयाँ प्रेस्क्रिप्सन चाहिन्छ।",
)
PRESCRIBER_REGISTRATION_REQUIRED = register(
    "PRESCRIBER_REGISTRATION_REQUIRED",
    400,
    "The prescriber's council registration number is required for this medicine.",
    "यो औषधिका लागि चिकित्सकको दर्ता नम्बर आवश्यक छ।",
)
MEDICINE_NOT_CLASSIFIED = register(
    "MEDICINE_NOT_CLASSIFIED",
    400,
    "This medicine has not been classified yet. Set its drug group before dispensing it.",
    "यो औषधिको वर्गीकरण गरिएको छैन। वितरण गर्नुअघि समूह तोक्नुहोस्।",
)
