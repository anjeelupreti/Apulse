"""Tenant registry and the organisation hierarchy inside a tenant.

    Tenant → LegalEntity (PAN / VAT registration) → Branch (premises, DDA licence) → Location

Registry tables (`Tenant`, `TenantDomain`, `TenantMembership`) are deliberately **not** under
row-level security: they must be readable before a tenant context exists, to resolve which tenant a
request belongs to and which tenants a person may sign in to. They hold no business data.
"""

from typing import ClassVar

from django.conf import settings
from django.core.validators import MinLengthValidator, RegexValidator
from django.db import models
from django.utils.timezone import now as utc_now  # `Tenant.timezone` would shadow the module
from django.utils.translation import gettext_lazy as _

from kernel.foundation.models import BaseModel
from kernel.geo.models import District, LocalLevel, Province

from .context import get_current_tenant_id
from .managers import AllTenantsManager, TenantManager

# Subdomains that must never become a tenant slug.
RESERVED_SLUGS = frozenset(
    {
        "www",
        "api",
        "app",
        "apps",
        "admin",
        "console",
        "static",
        "assets",
        "cdn",
        "mail",
        "smtp",
        "ftp",
        "status",
        "docs",
        "help",
        "support",
        "billing",
        "auth",
        "login",
        "public",
        "internal",
        "test",
        "staging",
        "dev",
        "demo",
        "npms",
        "apulse",
    }
)

slug_validator = RegexValidator(
    regex=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
    message=_("Use lowercase letters, digits and hyphens; start and end with a letter or digit."),
)
# Nepal PAN/VAT numbers are 9 digits. A VAT-registered business's VAT number is its PAN.
pan_validator = RegexValidator(regex=r"^\d{9}$", message=_("PAN must be exactly 9 digits."))


class TenantStatus(models.TextChoices):
    PROVISIONING = "provisioning", _("Provisioning")
    TRIAL = "trial", _("Trial")
    ACTIVE = "active", _("Active")
    GRACE = "grace", _("Grace period")
    SUSPENDED = "suspended", _("Suspended")
    CANCELLED = "cancelled", _("Cancelled")
    ARCHIVED = "archived", _("Archived")


class TenantTier(models.TextChoices):
    POOLED = "pooled", _("Pooled database")
    SILO = "silo", _("Dedicated database")
    ON_PREM = "on_prem", _("Customer premises")


class Tenant(BaseModel):
    """One customer account and the unit of billing, isolation and data export."""

    #: Statuses that still allow signing in, but block writes. Regulatory records must stay
    #: readable and exportable regardless of billing state — a pharmacy has to be able to produce
    #: its narcotic register for DDA even if its subscription has lapsed.
    READ_ONLY_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {TenantStatus.SUSPENDED, TenantStatus.CANCELLED}
    )
    #: Statuses that deny access entirely.
    CLOSED_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {TenantStatus.PROVISIONING, TenantStatus.ARCHIVED}
    )

    slug = models.SlugField(
        max_length=63, unique=True, validators=[slug_validator, MinLengthValidator(3)]
    )
    name = models.CharField(max_length=200)
    name_ne = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=20,
        choices=TenantStatus.choices,
        default=TenantStatus.PROVISIONING,
        db_index=True,
    )
    tier = models.CharField(max_length=20, choices=TenantTier.choices, default=TenantTier.POOLED)
    default_language = models.CharField(max_length=5, default="en")
    timezone = models.CharField(max_length=40, default="Asia/Kathmandu")

    trial_ends_on = models.DateField(null=True, blank=True)
    status_changed_at = models.DateTimeField(default=utc_now)
    status_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_read_only(self) -> bool:
        return self.status in self.READ_ONLY_STATUSES

    @property
    def is_accessible(self) -> bool:
        return self.status not in self.CLOSED_STATUSES

    def set_status(self, status: str, *, reason: str = "") -> None:
        self.status = status
        self.status_reason = reason
        self.status_changed_at = utc_now()
        self.save(update_fields=["status", "status_reason", "status_changed_at", "updated_at"])


class TenantDomain(BaseModel):
    """Hostnames that resolve to a tenant. Read before any tenant context exists."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="domains")
    domain = models.CharField(max_length=253, unique=True)
    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(is_primary=True),
                name="tenancy_one_primary_domain_per_tenant",
            )
        ]

    def __str__(self) -> str:
        return self.domain

    def save(self, *args: object, **kwargs: object) -> None:
        self.domain = self.domain.strip().lower()
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class TenantScopedModel(BaseModel):
    """Base class for everything that belongs to one tenant.

    Sets `tenant` from the active context on first save, so no caller can forget it, and pairs
    with a row-level security policy added in a migration (see `kernel.tenancy.rls`).
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+", db_index=True)

    objects: ClassVar[TenantManager] = TenantManager()
    all_tenants: ClassVar[AllTenantsManager] = AllTenantsManager()

    class Meta:
        abstract = True

    def save(self, *args: object, **kwargs: object) -> None:
        if self.tenant_id is None:
            from .context import require_current_tenant_id

            self.tenant_id = require_current_tenant_id()
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class TenantMembership(BaseModel):
    """Links a person to a tenant. Not row-level secured: sign-in has to list a user's tenants
    before any tenant context exists."""

    class Status(models.TextChoices):
        INVITED = "invited", _("Invited")
        ACTIVE = "active", _("Active")
        DISABLED = "disabled", _("Disabled")

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INVITED)
    default_branch = models.ForeignKey(
        "tenancy.Branch", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "user"], name="tenancy_unique_membership")
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.tenant}"


class LegalEntity(TenantScopedModel):
    """A registered business: the unit that IRD taxes and that issues invoices.

    A tenant may run more than one (for example a retail firm and a distribution firm).
    """

    name = models.CharField(max_length=200)
    name_ne = models.CharField(max_length=200, blank=True)
    pan = models.CharField(_("PAN"), max_length=9, validators=[pan_validator])
    # In Nepal a VAT-registered business's VAT number is its PAN, so there is no separate field;
    # this flag decides whether tax invoices show VAT.
    is_vat_registered = models.BooleanField(default=False)
    registration_number = models.CharField(max_length=50, blank=True)
    ird_office = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "legal entities"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "pan"], name="tenancy_unique_pan_per_tenant")
        ]

    def __str__(self) -> str:
        return self.name


class Branch(TenantScopedModel):
    """A physical premises. Each one holds its own DDA licence and its own invoice number series."""

    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT, related_name="branches")
    code = models.CharField(max_length=20, help_text=_("Short code used in document numbers."))
    name = models.CharField(max_length=200)
    name_ne = models.CharField(max_length=200, blank=True)

    province = models.ForeignKey(
        Province, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    district = models.ForeignKey(
        District, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    local_level = models.ForeignKey(
        LocalLevel, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    ward_no = models.PositiveSmallIntegerField(null=True, blank=True)
    street_address = models.CharField(max_length=200, blank=True)

    phone = models.CharField(max_length=16, blank=True)
    email = models.EmailField(blank=True)

    dda_licence_number = models.CharField(max_length=50, blank=True)
    dda_licence_expiry = models.DateField(null=True, blank=True)
    #: Retail pharmacy registration and renewal is handled at province level, so two branches of
    #: one chain may renew with different offices on different cycles (CR-DDA-05).
    dda_licence_authority = models.CharField(
        max_length=120,
        blank=True,
        help_text=_("The office that issued the licence: the province, or DDA centrally."),
    )

    is_warehouse = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "branches"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="tenancy_unique_branch_code_per_tenant"
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class LocationType(models.TextChoices):
    COUNTER = "counter", _("Sales counter")
    STORE = "store", _("Store room")
    RACK = "rack", _("Rack")
    SHELF = "shelf", _("Shelf")
    BIN = "bin", _("Bin")
    COLD_ROOM = "cold_room", _("Cold room")
    FRIDGE = "fridge", _("Refrigerator")
    FREEZER = "freezer", _("Freezer")
    LOCKED_CABINET = "locked_cabinet", _("Locked cabinet")
    WARD = "ward", _("Ward")
    OPERATING_THEATRE = "ot", _("Operating theatre")
    WAREHOUSE = "warehouse", _("Warehouse")


class TemperatureZone(models.TextChoices):
    AMBIENT = "ambient", _("Ambient")
    COOL = "cool", _("Cool (8-15°C)")
    COLD = "cold", _("Cold (2-8°C)")
    FROZEN = "frozen", _("Frozen (below 0°C)")


class Location(TenantScopedModel):
    """Where stock physically sits. Narcotics require a locked cabinet; vaccines a cold zone."""

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="locations")
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children"
    )
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=20, choices=LocationType.choices)
    temperature_zone = models.CharField(
        max_length=10, choices=TemperatureZone.choices, default=TemperatureZone.AMBIENT
    )
    is_sellable = models.BooleanField(
        default=True, help_text=_("Stock here can be sold. Quarantine locations set this to false.")
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["branch", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "branch", "code"], name="tenancy_unique_location_code_per_branch"
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


def current_tenant() -> Tenant | None:
    """The active tenant as a model instance, or None."""
    tenant_id = get_current_tenant_id()
    return Tenant.objects.filter(pk=tenant_id).first() if tenant_id else None
