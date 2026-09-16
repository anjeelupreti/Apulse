"""The catalogue of document types that carry a number.

Registered in code, like permissions, so a typo produces an error rather than silently starting a
second series that then runs alongside the real one.
"""

import re
from dataclasses import dataclass

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

#: Tokens a pattern may use. `{SEQ}` accepts a width, as in `{SEQ:6}`.
DEFAULT_PATTERN = "{TYPE}-{BRANCH}-{FY}-{SEQ:6}"


@dataclass(frozen=True, slots=True)
class DocumentType:
    code: str
    name_en: str
    name_ne: str
    #: Short form used by the `{TYPE}` token, e.g. INV.
    abbreviation: str
    pattern: str = DEFAULT_PATTERN
    #: True for anything IRD treats as a tax document. These may never have gaps, may never be
    #: reissued, and their series may not be edited once used.
    is_tax_document: bool = False
    description: str = ""


_registry: dict[str, DocumentType] = {}


def register(
    code: str,
    name_en: str,
    name_ne: str,
    *,
    abbreviation: str,
    pattern: str = DEFAULT_PATTERN,
    is_tax_document: bool = False,
    description: str = "",
) -> DocumentType:
    if not CODE_PATTERN.fullmatch(code):
        raise ValueError(f"Document type code must be '<module>.<document>': {code!r}")
    if not abbreviation.strip():
        raise ValueError(f"Document type {code} needs an abbreviation for the number")
    if not name_en.strip() or not name_ne.strip():
        raise ValueError(f"Document type {code} needs both English and Nepali names")
    if code in _registry:
        raise ValueError(f"Document type already registered: {code}")

    validate_pattern(pattern)
    document_type = DocumentType(
        code=code,
        name_en=name_en,
        name_ne=name_ne,
        abbreviation=abbreviation.strip().upper(),
        pattern=pattern,
        is_tax_document=is_tax_document,
        description=description,
    )
    _registry[code] = document_type
    return document_type


def get(code: str) -> DocumentType:
    try:
        return _registry[code]
    except KeyError:
        raise LookupError(f"Unregistered document type: {code}") from None


def exists(code: str) -> bool:
    return code in _registry


def all_types() -> tuple[DocumentType, ...]:
    return tuple(_registry.values())


# --------------------------------------------------------------------------- patterns
_TOKEN = re.compile(r"\{([A-Z_]+)(?::(\d+))?\}")
KNOWN_TOKENS = frozenset({"TYPE", "BRANCH", "FY", "FY_SHORT", "BS_YYYY", "SEQ"})


class PatternError(ValueError):
    """A number pattern is malformed."""


def validate_pattern(pattern: str) -> None:
    tokens = [match.group(1) for match in _TOKEN.finditer(pattern)]
    unknown = sorted(set(tokens) - KNOWN_TOKENS)
    if unknown:
        raise PatternError(
            f"Unknown token(s) {unknown} in pattern {pattern!r}. Available: {sorted(KNOWN_TOKENS)}"
        )
    if "SEQ" not in tokens:
        raise PatternError(
            f"Pattern {pattern!r} has no {{SEQ}}, so every document would get the same number."
        )
    if tokens.count("SEQ") > 1:
        raise PatternError(f"Pattern {pattern!r} uses {{SEQ}} more than once.")


def render(
    pattern: str,
    *,
    sequence: int,
    abbreviation: str = "",
    branch_code: str = "",
    fiscal_year: str = "",
    bs_year: str = "",
) -> str:
    """Fill a pattern in. `INV-KTM01-2082/83-000123`."""

    def replace(match: re.Match[str]) -> str:
        name, width = match.group(1), match.group(2)
        if name == "SEQ":
            return str(sequence).zfill(int(width)) if width else str(sequence)
        return {
            "TYPE": abbreviation,
            "BRANCH": branch_code,
            "FY": fiscal_year,
            "FY_SHORT": fiscal_year.replace("/", ""),
            "BS_YYYY": bs_year,
        }[name]

    return _TOKEN.sub(replace, pattern)


def autodiscover() -> None:
    """Import every installed app's `document_types` module."""
    from django.utils.module_loading import autodiscover_modules

    autodiscover_modules("document_types")
