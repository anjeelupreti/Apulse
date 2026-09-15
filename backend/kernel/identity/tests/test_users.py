import pytest
from django.db import IntegrityError, transaction

from kernel.identity.models import User
from shared.ids import uuid7_datetime

pytestmark = pytest.mark.django_db


def test_create_user_with_email_normalises_and_hashes_password():
    user = User.objects.create_user("  Ram.Sharma@Example.COM ", "s3cure-pass!", full_name="Ram")
    assert user.email == "ram.sharma@example.com"
    assert user.phone is None
    assert user.check_password("s3cure-pass!")
    assert user.password != "s3cure-pass!"
    assert not user.is_staff
    assert not user.is_superuser


def test_create_user_with_phone_only():
    user = User.objects.create_user(phone="981-2345678", password="x" * 12, full_name="Sita")
    assert user.email is None
    assert user.phone == "+9779812345678"


def test_blank_email_is_stored_as_null_so_many_phone_users_can_exist():
    User.objects.create_user("", phone="9812345671", full_name="A")
    User.objects.create_user("", phone="9812345672", full_name="B")
    assert User.objects.filter(email__isnull=True).count() == 2


def test_user_needs_email_or_phone():
    with pytest.raises(ValueError, match="email address or a phone number"):
        User.objects.create_user(full_name="Nobody")


def test_database_enforces_email_or_phone_even_when_manager_is_bypassed():
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(full_name="Bypass")


def test_email_is_unique_case_insensitively_through_manager():
    User.objects.create_user("hari@example.com", full_name="Hari")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("HARI@example.com", full_name="Hari 2")


def test_primary_key_is_uuid7():
    user = User.objects.create_user("gita@example.com", full_name="Gita")
    assert user.pk.version == 7
    assert uuid7_datetime(user.pk)


def test_create_superuser_sets_flags():
    admin = User.objects.create_superuser("admin@example.com", "admin-pass-123", full_name="Admin")
    assert admin.is_staff
    assert admin.is_superuser
