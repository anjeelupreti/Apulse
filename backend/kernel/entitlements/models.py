"""Modules and features as data, plus what each tenant is entitled to."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.foundation.models import BaseModel
from kernel.tenancy.models import TenantScopedModel

from .manifest import FeatureKind, ModuleStatus


class Module(BaseModel):
    """A sellable unit, synced from its code manifest. Platform-wide, not per tenant."""

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    name_ne = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=300, blank=True)
    version = models.CharField(max_length=20, default="1.0.0")
    status = models.CharField(
        max_length=12,
        choices=[(status.value, status.value) for status in ModuleStatus],
        default=ModuleStatus.GA.value,
    )
    is_core = models.BooleanField(default=False, help_text="Always installed; cannot be disabled.")
    depends_on = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name


class Feature(BaseModel):
    """One switch, ceiling or allowance inside a module."""

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="features")
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    name_ne = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=300, blank=True)
    kind = models.CharField(
        max_length=10,
        choices=[(kind.value, kind.value) for kind in FeatureKind],
        default=FeatureKind.BOOLEAN.value,
    )
    unit = models.CharField(max_length=30, blank=True)
    #: JSON so one column can hold false, 3 or null-for-unlimited.
    default_value = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class TenantModule(TenantScopedModel):
    """Whether a tenant has a module, and whether it is switched on right now.

    Installed-but-disabled keeps the data and hides the module — a downgrade must never delete a
    pharmacy's records.
    """

    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="+")
    is_enabled = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    installed_at = models.DateTimeField(auto_now_add=True)
    disabled_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "module"], name="entitlements_unique_tenant_module"
            )
        ]

    def __str__(self) -> str:
        return f"{self.module.code} ({'on' if self.is_enabled else 'off'})"


class GrantSource(models.TextChoices):
    PLAN = "plan", _("Included in the plan")
    ADDON = "addon", _("Purchased add-on")
    OVERRIDE = "override", _("Manual override")


class FeatureGrant(TenantScopedModel):
    """What a tenant has been given, and where it came from.

    Plan grants set the base, add-ons add to it, and an override replaces the result outright —
    which is how "Professional plus two extra branches" and "support granted this account an
    exception until Friday" are both expressible.
    """

    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="+")
    source = models.CharField(max_length=10, choices=GrantSource.choices)
    value = models.JSONField(null=True, blank=True)
    reason = models.CharField(max_length=300, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        indexes = [models.Index(fields=["tenant", "feature"])]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "feature", "source"],
                name="entitlements_unique_grant_per_source",
            )
        ]

    def __str__(self) -> str:
        return f"{self.feature.code} = {self.value} ({self.source})"


class FeatureFlag(BaseModel):
    """Operational control over a feature, independent of who bought it.

    A kill switch here turns something off for everyone without touching a single plan, which is
    what is needed at two in the morning when a feature is misbehaving.
    """

    feature_code = models.CharField(max_length=100, unique=True)
    is_killed = models.BooleanField(
        default=False, help_text="Off for everyone, whatever their plan says."
    )
    rollout_percent = models.PositiveSmallIntegerField(
        default=100, help_text="Share of accounts the feature reaches, chosen stably per account."
    )
    allowed_tenants = models.JSONField(default=list, blank=True)
    denied_tenants = models.JSONField(default=list, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)

    def __str__(self) -> str:
        return f"{self.feature_code} ({'killed' if self.is_killed else self.rollout_percent}%)"


class UsageMeter(TenantScopedModel):
    """How much of a quota a tenant has consumed in a period."""

    metric = models.CharField(max_length=100)
    period_start = models.DateField()
    period_end = models.DateField()
    value = models.BigIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["tenant", "metric", "-period_start"])]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "metric", "period_start"],
                name="entitlements_unique_meter_period",
            )
        ]

    def __str__(self) -> str:
        return f"{self.metric}: {self.value}"
