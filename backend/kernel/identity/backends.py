"""Authentication backend: sign in with an email address **or** a phone number.

Counter staff in Nepal frequently have no email address, so the phone number is a first-class
credential rather than a fallback.
"""

from typing import Any

from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

from shared.phone import normalize_phone

from .managers import normalize_email_address
from .models import User


def find_user_by_identifier(identifier: str) -> User | None:
    """Look up by email or phone, applying the same normalisation used when the value was stored."""
    identifier = (identifier or "").strip()
    if not identifier:
        return None

    if "@" in identifier:
        email = normalize_email_address(identifier)
        return User.objects.filter(email=email).first() if email else None

    try:
        phone = normalize_phone(identifier)
    except ValueError:
        return None
    return User.objects.filter(phone=phone).first() if phone else None


class EmailOrPhoneBackend(ModelBackend):
    def authenticate(
        self,
        request: HttpRequest | None = None,  # noqa: ARG002 (Django's backend signature)
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> User | None:
        identifier = username or kwargs.get("identifier")
        if not identifier or password is None:
            return None

        user = find_user_by_identifier(identifier)
        if user is None:
            # Hash anyway: a missing account must not answer measurably faster than a wrong
            # password, or the timing difference becomes an account-enumeration oracle.
            User().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
