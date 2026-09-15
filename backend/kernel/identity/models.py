from typing import ClassVar

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.foundation.models import BaseModel
from shared.phone import normalize_phone

from .managers import UserManager, normalize_email_address


class Language(models.TextChoices):
    ENGLISH = "en", "English"
    NEPALI = "ne", "नेपाली"


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """A person. Tenant access comes from memberships (kernel.tenancy, Phase 2), not from this row.

    Counter staff often have no email, so login is by email *or* phone; at least one is required.
    """

    email = models.EmailField(_("email"), unique=True, null=True, blank=True)
    # NULL (not "") keeps the unique constraint usable for users without a phone.
    phone = models.CharField(_("phone"), max_length=16, unique=True, null=True, blank=True)
    full_name = models.CharField(_("full name"), max_length=150)
    full_name_ne = models.CharField(_("full name (Nepali)"), max_length=150, blank=True)
    preferred_language = models.CharField(
        max_length=5, choices=Language.choices, default=Language.ENGLISH
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False, help_text="Can log into the internal Django admin. Not a product role."
    )

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(email__isnull=False) | models.Q(phone__isnull=False),
                name="identity_user_email_or_phone_required",
            ),
        ]

    def __str__(self) -> str:
        return self.full_name or self.email or self.phone or str(self.pk)

    def clean(self) -> None:
        super().clean()
        self.email = normalize_email_address(self.email)
        self.phone = normalize_phone(self.phone)
