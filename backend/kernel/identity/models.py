from datetime import date
from typing import ClassVar

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
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


class TwoFactorDevice(BaseModel):
    """An authenticator app enrolled by one user."""

    # TODO(X-SEC): move `secret` to field-level encryption with a KMS-managed key. Anyone with
    # read access to this table can currently mint valid codes, so treat it like a password hash
    # table until that lands.
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="two_factor")
    secret = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    #: The TOTP time step most recently accepted, so one code cannot be replayed inside its window.
    last_used_timestep = models.BigIntegerField(null=True, blank=True)

    def __str__(self) -> str:
        return f"2FA for {self.user}"

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None


class RecoveryCode(BaseModel):
    """Single-use fallback for a lost authenticator. Stored hashed, exactly like a password."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=128)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "used_at"])]

    def __str__(self) -> str:
        return f"Recovery code for {self.user}"


class CredentialType(models.TextChoices):
    """Professional registers. Exact council for each profession: see CR-NPC-01 / CR-NMC-01."""

    PHARMACY_COUNCIL = "npc", _("Nepal Pharmacy Council")
    MEDICAL_COUNCIL = "nmc", _("Nepal Medical Council")
    NURSING_COUNCIL = "nnc", _("Nepal Nursing Council")
    HEALTH_PROFESSIONAL_COUNCIL = "nhpc", _("Nepal Health Professional Council")
    OTHER = "other", _("Other")


class CredentialStatus(models.TextChoices):
    PENDING = "pending", _("Awaiting verification")
    VERIFIED = "verified", _("Verified")
    REJECTED = "rejected", _("Rejected")


class UserCredential(BaseModel):
    """A professional registration held by a person.

    Global rather than per-tenant: a pharmacist's council registration is a fact about them, not
    about the pharmacy that employs them, and a locum working at three shops registers once.

    Some actions require one of these regardless of role — only a registered pharmacist may
    dispense a Samuha KA medicine, however the owner has configured permissions.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="credentials")
    type = models.CharField(max_length=10, choices=CredentialType.choices)
    registration_number = models.CharField(max_length=50)
    status = models.CharField(
        max_length=10, choices=CredentialStatus.choices, default=CredentialStatus.PENDING
    )
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_note = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "type", "registration_number"],
                name="identity_unique_credential",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_type_display()} {self.registration_number}"

    def is_valid_on(self, on_date: date | None = None) -> bool:
        """Verified and not expired. An expired registration is not a registration."""
        if self.status != CredentialStatus.VERIFIED:
            return False
        if self.expires_on is None:
            return True
        return self.expires_on >= (on_date or timezone.localdate())


class LoginOutcome(models.TextChoices):
    SUCCESS = "success", _("Signed in")
    INVALID_CREDENTIALS = "invalid_credentials", _("Wrong identifier or password")
    LOCKED_OUT = "locked_out", _("Too many attempts")
    DISABLED = "disabled", _("Account disabled")
    NO_TENANT_ACCESS = "no_tenant_access", _("Not a member of this account")
    TWO_FACTOR_REQUIRED = "two_factor_required", _("Password accepted, code required")
    TWO_FACTOR_FAILED = "two_factor_failed", _("Wrong verification code")
    RECOVERY_CODE_USED = "recovery_code_used", _("Signed in with a recovery code")


class LoginAttempt(BaseModel):
    """Security log of every sign-in attempt, successful or not.

    Kept out of row-level security because an attempt may name a tenant the person has no access
    to — that is precisely the case worth recording. The tenant is denormalised to a slug so the
    record survives the tenant being removed.
    """

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="login_attempts"
    )
    identifier = models.CharField(max_length=254)
    tenant_slug = models.CharField(max_length=63, blank=True)
    outcome = models.CharField(max_length=30, choices=LoginOutcome.choices, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["identifier", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.identifier} — {self.outcome}"
