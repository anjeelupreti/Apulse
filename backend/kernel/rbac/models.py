"""Roles, the permissions they carry, and who holds them where."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.tenancy.models import TenantScopedModel


class Role(TenantScopedModel):
    """A named set of permissions inside one tenant.

    System roles are seeded per tenant and kept in step with the code by `sync_system_roles`.
    They are not editable — a pharmacy that wants a variation clones one instead, so an upgrade
    that adds permissions to "Pharmacist" cannot silently overwrite local changes.
    """

    code = models.SlugField(max_length=50)
    name = models.CharField(max_length=100)
    name_ne = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=300, blank=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="rbac_unique_role_code")
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def permission_codes(self) -> set[str]:
        return set(self.permissions.values_list("code", flat=True))


class RolePermission(TenantScopedModel):
    """One permission granted to one role.

    The code is stored as text rather than a foreign key: permissions live in code, and an
    uninstalled module's permissions should sit dormant rather than vanish from every role.
    """

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    code = models.CharField(max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "role", "code"], name="rbac_unique_role_permission"
            )
        ]

    def __str__(self) -> str:
        return f"{self.role.code}: {self.code}"


class AssignmentScope(models.TextChoices):
    TENANT = "tenant", _("Whole account")
    LEGAL_ENTITY = "legal_entity", _("One business")
    BRANCH = "branch", _("One branch")


class RoleAssignment(TenantScopedModel):
    """A person holding a role, optionally limited to one business or branch.

    `expires_at` exists for the cases that actually occur: a DDA inspector given read access for
    the duration of a visit, and a locum pharmacist covering a week.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_assignments"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="assignments")
    scope = models.CharField(
        max_length=20, choices=AssignmentScope.choices, default=AssignmentScope.TENANT
    )
    legal_entity = models.ForeignKey(
        "tenancy.LegalEntity", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    branch = models.ForeignKey(
        "tenancy.Branch", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=300, blank=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "user"])]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user", "role", "scope", "legal_entity", "branch"],
                name="rbac_unique_assignment",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(scope="tenant", legal_entity__isnull=True, branch__isnull=True)
                    | models.Q(
                        scope="legal_entity", legal_entity__isnull=False, branch__isnull=True
                    )
                    | models.Q(scope="branch", branch__isnull=False)
                ),
                name="rbac_assignment_scope_matches_target",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} as {self.role.code}"
