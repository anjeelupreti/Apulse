import pytest

from shared.errors import DomainError, all_codes, codes, get, register


def test_every_registered_code_has_both_languages_and_error_status():
    registered = all_codes()
    assert registered
    for error in registered:
        assert error.message_en.strip()
        assert error.message_ne.strip()
        assert 400 <= error.http_status <= 599


def test_duplicate_registration_is_rejected():
    with pytest.raises(ValueError, match="already registered"):
        register("NOT_FOUND", 404, "Not found.", "फेला परेन।")


@pytest.mark.parametrize("bad_code", ["not_upper", "TRAILING_", "_LEADING", "HAS SPACE"])
def test_code_format_is_enforced(bad_code):
    with pytest.raises(ValueError, match="UPPER_SNAKE_CASE"):
        register(bad_code, 400, "x", "x")


def test_nepali_message_is_required():
    with pytest.raises(ValueError, match="English and Nepali"):
        register("SHARED_TEST_MISSING_NE", 400, "Message", " ")


def test_unregistered_code_lookup_fails_loudly():
    with pytest.raises(LookupError, match="Unregistered error code"):
        get("DOES_NOT_EXIST")


def test_domain_error_uses_catalogue_message_by_default():
    error = DomainError("VERSION_CONFLICT", details=[{"field": "version", "code": "stale"}])
    assert error.error is codes.VERSION_CONFLICT
    assert error.http_status == 409
    assert error.message == codes.VERSION_CONFLICT.message_en
    assert error.details == [{"field": "version", "code": "stale"}]
