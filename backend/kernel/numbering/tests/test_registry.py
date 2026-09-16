import pytest

from kernel.numbering import registry
from kernel.numbering.registry import PatternError, render, validate_pattern


@pytest.mark.parametrize(
    "bad_code", ["nodots", "Upper.Case", "sales.", ".invoice", "sales.invoice.extra"]
)
def test_codes_must_name_a_module_and_a_document(bad_code, document_types):
    with pytest.raises(ValueError, match=r"<module>\.<document>"):
        registry.register(bad_code, "X", "X", abbreviation="X")


def test_a_type_cannot_be_registered_twice(document_types):
    with pytest.raises(ValueError, match="already registered"):
        registry.register("sales.invoice", "Again", "फेरि", abbreviation="INV")


def test_both_languages_are_required(document_types):
    with pytest.raises(ValueError, match="English and Nepali"):
        registry.register("sales.quote", "Quote", "  ", abbreviation="QT")


def test_an_abbreviation_is_required(document_types):
    with pytest.raises(ValueError, match="abbreviation"):
        registry.register("sales.quote", "Quote", "कोटेशन", abbreviation=" ")


def test_unknown_types_fail_loudly(document_types):
    with pytest.raises(LookupError, match="Unregistered document type"):
        registry.get("sales.nothing")


# --------------------------------------------------------------------------- patterns
def test_a_pattern_without_a_sequence_is_rejected():
    """Otherwise every document would be handed the same number."""
    with pytest.raises(PatternError, match=r"no \{SEQ\}"):
        validate_pattern("INV-{BRANCH}-{FY}")


def test_a_pattern_with_two_sequences_is_rejected():
    with pytest.raises(PatternError, match="more than once"):
        validate_pattern("{SEQ}-{SEQ:4}")


def test_unknown_tokens_are_rejected_with_the_list_of_real_ones():
    with pytest.raises(PatternError, match="Unknown token"):
        validate_pattern("{INVOICE_NO}-{SEQ}")


def test_rendering_a_full_number():
    assert (
        render(
            "{TYPE}-{BRANCH}-{FY}-{SEQ:6}",
            sequence=123,
            abbreviation="INV",
            branch_code="KTM01",
            fiscal_year="2082/83",
        )
        == "INV-KTM01-2082/83-000123"
    )


def test_the_sequence_width_is_respected():
    assert render("{SEQ:4}", sequence=7) == "0007"
    assert render("{SEQ}", sequence=7) == "7"


def test_a_sequence_longer_than_its_width_is_not_truncated():
    """Better a wider number than a duplicate one."""
    assert render("{SEQ:3}", sequence=12345) == "12345"


def test_the_short_fiscal_year_token_drops_the_slash():
    assert render("{FY_SHORT}/{SEQ}", sequence=1, fiscal_year="2082/83") == "208283/1"


def test_the_bs_year_token():
    assert render("{BS_YYYY}-{SEQ}", sequence=1, bs_year="2082") == "2082-1"
