"""Answering "may this person do this, here?".

Deliberately uncached. An earlier version memoised the answer on the user object, which leaked one
tenant's permissions into another whenever a user instance outlived a single request. Permission
checks are a handful of small indexed queries; a stale permission is a security bug. Caching
belongs with the entitlement resolver (M2.5), where invalidation is explicit.
"""

from typing import cast
from uuid import UUID

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q
from django.utils import timezone

from kernel.identity.models import CredentialStatus, User, UserCredential

from . import registry
from .models import AssignmentScope, RoleAssignment

#: Views hand us whoever is on the request, which may be nobody.
AnyUser = AbstractBaseUser | AnonymousUser


def _active_assignments(user: User) -> list[RoleAssignment]:
    """Live assignments for the current tenant. Row-level security scopes this to that tenant."""
    now = timezone.now()
    return list(
        RoleAssignment.objects.filter(user=user, role__is_active=True)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .select_related("role")
        .prefetch_related("role__permissions")
    )


def permissions_for(user: AnyUser) -> frozenset[str]:
    """Every permission this user holds in the current tenant, from any scope."""
    if not user.is_authenticated:
        return frozenset()
    codes: set[str] = set()
    for assignment in _active_assignments(cast("User", user)):
        codes.update(permission.code for permission in assignment.role.permissions.all())
    return frozenset(codes)


def branch_ids_for(user: AnyUser, permission: str | None = None) -> frozenset[UUID] | None:
    """Branches this permission applies in.

    `None` means "not limited to particular branches" — the user holds the permission at account
    or business level. An empty set means they hold it nowhere.
    """
    limited: set[UUID] = set()
    for assignment in _active_assignments(cast("User", user)):
        if permission is not None and permission not in assignment.role.permission_codes:
            continue
        if assignment.scope != AssignmentScope.BRANCH:
            return None
        if assignment.branch_id is not None:
            limited.add(assignment.branch_id)
    return frozenset(limited)


def has_permission(user: AnyUser, code: str, *, branch_id: UUID | None = None) -> bool:
    """Whether the user may perform this action, optionally in one branch.

    A permission that names a required professional registration is refused unless the user holds
    that registration, verified and unexpired — no role configuration can override it.
    """
    if not user.is_authenticated:
        return False
    if code not in permissions_for(user):
        return False

    if branch_id is not None:
        allowed = branch_ids_for(user, code)
        if allowed is not None and branch_id not in allowed:
            return False

    required_credential = registry.get(code).requires_credential
    return not (required_credential and not holds_credential(user, required_credential))


def holds_credential(user: AnyUser, credential_type: str) -> bool:
    """A verified, unexpired professional registration of this type."""
    today = timezone.localdate()
    return (
        UserCredential.objects.filter(
            user=cast("User", user), type=credential_type, status=CredentialStatus.VERIFIED
        )
        .filter(Q(expires_on__isnull=True) | Q(expires_on__gte=today))
        .exists()
    )


def missing_permissions(user: AnyUser, codes: tuple[str, ...]) -> tuple[str, ...]:
    held = permissions_for(user)
    return tuple(code for code in codes if code not in held)
