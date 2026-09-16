"""Where a setting's value is stored, once somebody has set one."""

from django.conf import settings as django_settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.tenancy.models import TenantScopedModel

from .registry import Scope

#: The scopes a value can actually be stored at today. `Scope.PLATFORM` is part of the resolution
#: chain but has no row: the platform default *is* the default declared in code, which means a
#: release that improves a default improves it for everyone who never overrode it. A platform
#: value stored per-row would need a tenant-less row, and a tenant-less row cannot be protected by
#: row-level security without also letting one tenant write a value that lands on everybody else.
#: Overriding a default centrally belongs to the control plane (Phase 3), which has its own trail.
STORABLE_SCOPES: tuple[Scope, ...] = (Scope.TENANT, Scope.LEGAL_ENTITY, Scope.BRANCH, Scope.USER)


class SettingValue(TenantScopedModel):
    """One value, set at one scope, belonging to one account.

    Only rows somebody actually set exist. A setting left alone has no row anywhere and resolves
    to the default declared in code.
    """

    key = models.CharField(max_length=120, db_index=True)
    scope = models.CharField(max_length=20, choices=[(scope, scope) for scope in STORABLE_SCOPES])
    #: Which branch, legal entity or user this value is for. Empty at tenant scope.
    scope_id = models.CharField(
        max_length=64, blank=True, help_text=_("Empty when the value applies to the whole account.")
    )

    #: Stored as text whatever the kind, so one column serves all of them and a value read back is
    #: always the shape it was written in. The registry says how to read it.
    value = models.TextField()
    reason = models.CharField(max_length=300, blank=True)
    set_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["key", "scope"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "key", "scope", "scope_id"],
                name="settings_one_value_per_scope",
            ),
            #: A value for the whole account names no target; a narrower one must name its own.
            models.CheckConstraint(
                condition=models.Q(scope="tenant", scope_id="") | ~models.Q(scope="tenant"),
                name="settings_account_wide_values_have_no_target",
            ),
            models.CheckConstraint(
                condition=~models.Q(scope__in=["legal_entity", "branch", "user"], scope_id=""),
                name="settings_narrow_values_name_their_target",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "key"])]

    def __str__(self) -> str:
        return f"{self.key} = {self.value} ({self.scope})"
