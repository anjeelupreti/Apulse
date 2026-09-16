"""DRF permission classes. Authorisation is always decided server-side."""

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from kernel.tenancy import errors as tenancy_errors
from kernel.tenancy.models import Tenant
from shared.errors import DomainError

from .. import resolver


class RequireTenant(BasePermission):
    """The request must be for a resolved tenant.

    Use on anything that touches tenant data: without a tenant context those queries return
    nothing, which would otherwise look like an empty pharmacy rather than a misrouted request.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:  # noqa: ARG002 (DRF)
        if not isinstance(getattr(request, "tenant", None), Tenant):
            raise DomainError(tenancy_errors.TENANT_NOT_FOUND)
        return True


class HasPermission(BasePermission):
    """Checks the codes listed in the view's `required_permissions`."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        codes: tuple[str, ...] = tuple(getattr(view, "required_permissions", ()))
        if not codes:
            return True
        return all(resolver.has_permission(request.user, code) for code in codes)


def RequirePermission(*codes: str) -> type[BasePermission]:  # noqa: N802 (a class factory)
    """Inline form: `permission_classes = [RequirePermission("tenancy.branch.manage")]`."""

    class _RequirePermission(BasePermission):
        def has_permission(self, request: Request, view: APIView) -> bool:  # noqa: ARG002 (DRF)
            return all(resolver.has_permission(request.user, code) for code in codes)

    return _RequirePermission


def scoped_to_branches(user: Any, permission: str) -> frozenset[Any] | None:
    """Branch ids a queryset should be limited to, or None for no branch limit."""
    return resolver.branch_ids_for(user, permission)
