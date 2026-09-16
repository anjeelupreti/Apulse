"""Creating roles, keeping the built-in ones in step, and granting or revoking them."""

from datetime import datetime
from typing import cast

import structlog
from django.db import transaction

from kernel.identity.models import User
from kernel.tenancy.models import Branch, LegalEntity, Tenant

from . import registry, system_roles
from .models import AssignmentScope, Role, RoleAssignment, RolePermission

logger = structlog.get_logger(__name__)


class UnknownPermissionError(ValueError):
    """A role was given a permission nothing in the codebase checks."""


@transaction.atomic
def sync_system_roles(tenant: Tenant) -> list[Role]:
    """Create or update the built-in roles for a tenant.

    Idempotent, and safe to re-run after a release adds permissions or installs a module. Only
    system roles are touched; anything a pharmacy created itself is left alone.
    """
    synced = []
    for definition in system_roles.SYSTEM_ROLES:
        role, _ = Role.all_tenants.update_or_create(
            tenant=tenant,
            code=definition.code,
            defaults={
                "name": definition.name_en,
                "name_ne": definition.name_ne,
                "description": definition.description,
                "is_system": True,
            },
        )
        _replace_permissions(role, definition.resolve())
        synced.append(role)
    return synced


def _replace_permissions(role: Role, codes: frozenset[str]) -> None:
    existing = set(RolePermission.all_tenants.filter(role=role).values_list("code", flat=True))
    to_add = codes - existing
    to_remove = existing - codes
    if to_remove:
        RolePermission.all_tenants.filter(role=role, code__in=to_remove).delete()
    if to_add:
        RolePermission.all_tenants.bulk_create(
            [RolePermission(tenant_id=role.tenant_id, role=role, code=code) for code in to_add]
        )


@transaction.atomic
def create_role(
    *, code: str, name: str, permissions: tuple[str, ...], name_ne: str = "", description: str = ""
) -> Role:
    _require_known_permissions(permissions)
    role = cast(
        "Role",
        Role.objects.create(
            code=code, name=name, name_ne=name_ne, description=description, is_system=False
        ),
    )
    _replace_permissions(role, frozenset(permissions))
    return role


@transaction.atomic
def set_role_permissions(role: Role, permissions: tuple[str, ...]) -> Role:
    if role.is_system:
        raise ValueError(
            f"{role.code} is a built-in role and is kept in step with the code. "
            "Clone it to make a variation."
        )
    _require_known_permissions(permissions)
    _replace_permissions(role, frozenset(permissions))
    return role


@transaction.atomic
def clone_role(role: Role, *, code: str, name: str) -> Role:
    """Copy a role, including built-in ones, so a pharmacy can adjust it."""
    return create_role(
        code=code,
        name=name,
        permissions=tuple(sorted(role.permission_codes)),
        description=f"Based on {role.name}",
    )


def _require_known_permissions(permissions: tuple[str, ...]) -> None:
    unknown = [code for code in permissions if not registry.exists(code)]
    if unknown:
        raise UnknownPermissionError(
            f"Nothing in the codebase checks these permissions: {sorted(unknown)}"
        )


@transaction.atomic
def assign_role(
    *,
    user: User,
    role: Role,
    scope: str = AssignmentScope.TENANT,
    legal_entity: LegalEntity | None = None,
    branch: Branch | None = None,
    granted_by: User | None = None,
    expires_at: datetime | None = None,
    reason: str = "",
) -> RoleAssignment:
    """Give a person a role, optionally limited to one business or branch and to a period."""
    if scope == AssignmentScope.BRANCH and branch is None:
        raise ValueError("A branch-scoped assignment needs a branch.")
    if scope == AssignmentScope.LEGAL_ENTITY and legal_entity is None:
        raise ValueError("A business-scoped assignment needs a legal entity.")
    if scope == AssignmentScope.TENANT and (branch is not None or legal_entity is not None):
        raise ValueError("An account-wide assignment must not name a branch or business.")

    assignment, created = cast(
        "tuple[RoleAssignment, bool]",
        RoleAssignment.objects.get_or_create(
            user=user,
            role=role,
            scope=scope,
            legal_entity=legal_entity,
            branch=branch,
            defaults={"granted_by": granted_by, "expires_at": expires_at, "reason": reason},
        ),
    )
    if not created:
        assignment.expires_at = expires_at
        assignment.reason = reason
        assignment.save(update_fields=["expires_at", "reason", "updated_at"])

    logger.info(
        "role_assigned",
        user_id=str(user.pk),
        role=role.code,
        scope=scope,
        expires_at=expires_at.isoformat() if expires_at else None,
    )
    return assignment


def revoke_role(assignment: RoleAssignment) -> None:
    logger.info("role_revoked", user_id=str(assignment.user_id), role=assignment.role.code)
    assignment.delete()
