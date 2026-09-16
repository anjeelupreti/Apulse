import pytest

from kernel.identity.backends import EmailOrPhoneBackend, find_user_by_identifier
from kernel.identity.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(
        "Ram.Sharma@Example.com", "correct-horse-battery", full_name="Ram Sharma"
    )


@pytest.fixture
def phone_user():
    return User.objects.create_user(
        phone="9812345678", password="correct-horse-battery", full_name="Sita Counter"
    )


def test_email_lookup_ignores_case_and_spacing(user):
    assert find_user_by_identifier("  RAM.SHARMA@EXAMPLE.COM ") == user


def test_phone_lookup_accepts_the_local_format_people_actually_type(phone_user):
    for typed in ("9812345678", "+977 9812345678", "981-234-5678"):
        assert find_user_by_identifier(typed) == phone_user


def test_unparseable_phone_returns_nothing_rather_than_raising():
    assert find_user_by_identifier("12345") is None


def test_unknown_identifier_returns_nothing(user):
    assert find_user_by_identifier("nobody@example.com") is None


def test_backend_authenticates_by_email(user):
    assert (
        EmailOrPhoneBackend().authenticate(
            None, username="ram.sharma@example.com", password="correct-horse-battery"
        )
        == user
    )


def test_backend_authenticates_by_phone(phone_user):
    authenticated = EmailOrPhoneBackend().authenticate(
        None, username="9812345678", password="correct-horse-battery"
    )
    assert authenticated == phone_user


def test_backend_rejects_a_wrong_password(user):
    assert EmailOrPhoneBackend().authenticate(None, username=user.email, password="wrong") is None


def test_backend_rejects_a_disabled_account(user):
    user.is_active = False
    user.save(update_fields=["is_active"])
    result = EmailOrPhoneBackend().authenticate(
        None, username=user.email, password="correct-horse-battery"
    )
    assert result is None
