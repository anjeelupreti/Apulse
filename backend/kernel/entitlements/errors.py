"""Entitlement error codes.

Wording matters here: these are the messages a paying pharmacy sees when something is not
available, so they say what to do rather than merely refusing.
"""

from shared.errors import register

FEATURE_NOT_ENTITLED = register(
    "FEATURE_NOT_ENTITLED",
    403,
    "This is not included in your current plan.",
    "यो सुविधा तपाईंको हालको योजनामा समावेश छैन।",
)
FEATURE_LIMIT_REACHED = register(
    "FEATURE_LIMIT_REACHED",
    403,
    "You have reached the limit included in your plan.",
    "तपाईंको योजनामा समावेश सीमा पुगिसक्यो।",
)
MODULE_NOT_ENABLED = register(
    "MODULE_NOT_ENABLED",
    403,
    "This part of the system is switched off for your account.",
    "प्रणालीको यो भाग तपाईंको खाताका लागि बन्द छ।",
)
