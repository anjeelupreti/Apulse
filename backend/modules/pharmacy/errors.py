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

CONTROLLED_DRUG_NEEDS_LOCKED_STORAGE = register(
    "CONTROLLED_DRUG_NEEDS_LOCKED_STORAGE",
    400,
    "Controlled drugs must be put away in a locked cabinet. Choose that location and try again.",
    "नियन्त्रित औषधि लक भएको दराजमा राख्नुपर्छ। सोही स्थान छानेर पुनः प्रयास गर्नुहोस्।",
)
PHARMACIST_REGISTRATION_REQUIRED = register(
    "PHARMACIST_REGISTRATION_REQUIRED",
    403,
    "Only a registered pharmacist may hand over this medicine.",
    "यो औषधि दर्ता भएका फार्मासिस्टले मात्र दिन सक्छन्।",
)
REGISTER_CORRECTION_NEEDS_REASON = register(
    "REGISTER_CORRECTION_NEEDS_REASON",
    400,
    "A correction to the narcotic register needs a reason.",
    "लागूऔषध अभिलेख सच्याउन कारण उल्लेख गर्नुपर्छ।",
)
REGISTER_COUNT_NEEDS_WITNESS = register(
    "REGISTER_COUNT_NEEDS_WITNESS",
    400,
    "A stock count of controlled drugs must be witnessed. Record the witness's name.",
    "नियन्त्रित औषधिको गणना साक्षीको उपस्थितिमा हुनुपर्छ। साक्षीको नाम उल्लेख गर्नुहोस्।",
)
REGISTER_ENTRY_IS_EMPTY = register(
    "REGISTER_ENTRY_IS_EMPTY",
    400,
    "A register entry cannot be for zero quantity.",
    "अभिलेखमा शून्य परिमाण राख्न मिल्दैन।",
)
REGISTER_COUNT_IS_PER_BATCH = register(
    "REGISTER_COUNT_IS_PER_BATCH",
    400,
    "This medicine is held in batches. Count each batch and record it against that batch.",
    "यो औषधि ब्याच अनुसार राखिएको छ। प्रत्येक ब्याच छुट्टै गणना गरी सोही ब्याचमा अभिलेख गर्नुहोस्।",
)
