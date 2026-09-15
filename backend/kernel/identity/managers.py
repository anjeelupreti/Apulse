from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

from shared.phone import normalize_phone

if TYPE_CHECKING:
    from .models import User


def normalize_email_address(email: str | None) -> str | None:
    """Store emails fully lower-cased so lookups are case-insensitive; blank becomes NULL."""
    if email is None:
        return None
    email = email.strip().lower()
    return email or None


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create_user(
        self, email: str | None, phone: str | None, password: str | None, **extra: Any
    ) -> "User":
        email = normalize_email_address(email)
        phone = normalize_phone(phone)
        if not email and not phone:
            raise ValueError("A user needs an email address or a phone number.")
        user = self.model(email=email, phone=phone, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str | None = None,
        password: str | None = None,
        *,
        phone: str | None = None,
        **extra: Any,
    ) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, phone, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        """Django-admin superuser (internal debugging). Platform staff live in the control plane."""
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create_user(email, extra.pop("phone", None), password, **extra)
