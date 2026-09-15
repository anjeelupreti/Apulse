"""Phone number normalisation to E.164, with Nepal as the default country."""

import re

NEPAL_COUNTRY_CODE = "977"
_STRIP = re.compile(r"[\s\-().]")


def normalize_phone(raw: str | None) -> str | None:
    """Normalise to E.164 (``+9779812345678``). Returns ``None`` for empty input.

    Accepted inputs: ``9812345678``, ``+977 981-2345678``, ``009779812345678``,
    ``9779812345678``, landlines with trunk prefix such as ``01-4412345``.
    """
    if raw is None:
        return None
    value = _STRIP.sub("", raw)
    if not value:
        return None
    if value.startswith("00"):
        value = "+" + value[2:]

    if value.startswith("+"):
        digits = value[1:]
    elif value.startswith(NEPAL_COUNTRY_CODE) and len(value) == 13:
        digits = value
    elif len(value) == 10 and value.startswith("9"):
        digits = NEPAL_COUNTRY_CODE + value
    elif value.startswith("0") and 8 <= len(value) <= 10:
        digits = NEPAL_COUNTRY_CODE + value[1:]
    else:
        raise ValueError(f"Unrecognised phone number format: {raw!r}")

    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise ValueError(f"Unrecognised phone number format: {raw!r}")
    return "+" + digits
