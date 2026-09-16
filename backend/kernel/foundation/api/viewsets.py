"""The base every tenant endpoint is built on.

Each of the pieces below exists somewhere already — permissions, pagination, filtering, the error
envelope, idempotency, versioning. Wiring them together in one place is the point: a view that has
to remember to apply branch scoping is a view that will one day forget, and the failure is silent
and looks like a working screen.

A view says what it is about — the permissions it needs, the field its dates live on, the fields
worth searching — and gets the rest.
"""

from typing import Any, cast

from rest_framework import mixins, viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.request import Request
from rest_framework.response import Response

from kernel.rbac.api.permissions import HasPermission, RequireTenant

from . import concurrency, idempotency
from .filters import BranchScopeFilter, DateRangeFilter, UpdatedSinceFilter


class TenantAPIView(viewsets.GenericViewSet[Any]):
    """Shared behaviour for anything serving one pharmacy's data."""

    permission_classes = [RequireTenant, HasPermission]
    filter_backends = [
        BranchScopeFilter,
        UpdatedSinceFilter,
        DateRangeFilter,
        SearchFilter,
        OrderingFilter,
    ]

    #: Permission codes the whole viewset needs. Per-action codes go in `action_permissions`.
    required_permissions: tuple[str, ...] = ()
    #: `{"create": ("sales.invoice.issue",)}` — checked in addition to the ones above.
    action_permissions: dict[str, tuple[str, ...]] = {}
    #: Which permission decides the branches this user may see rows from.
    branch_scope_permission: str | None = None
    branch_field = "branch"
    date_field: str | None = None

    def get_permissions(self) -> Any:
        extra = self.action_permissions.get(getattr(self, "action", "") or "", ())
        if extra:
            # Combined rather than replaced: an action's own requirement is on top of the
            # viewset's, never instead of it.
            self.required_permissions = tuple({*self.required_permissions, *extra})
        return super().get_permissions()

    @property
    def tenant_id(self) -> Any:
        return getattr(getattr(self.request, "tenant", None), "pk", None)

    def audit_actor(self) -> Any:
        user = getattr(self.request, "user", None)
        return user if getattr(user, "is_authenticated", False) else None


class IdempotentCreateMixin:
    """A create that can be retried without creating a second one.

    On by default for anything that writes, because the client that most needs it — a till on a
    bad connection — is also the least likely to remember to ask.
    """

    idempotency_required = False

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        tenant_id = getattr(getattr(request, "tenant", None), "pk", None)
        stored = idempotency.replay(
            request, tenant_id=tenant_id, required=self.idempotency_required
        )
        if stored is not None:
            return stored
        try:
            response = cast("Response", super().create(request, *args, **kwargs))  # type: ignore[misc]
        except Exception:
            idempotency.release(request, tenant_id=tenant_id)
            raise
        idempotency.remember(request, response, tenant_id=tenant_id)
        return response


class VersionedUpdateMixin(concurrency.VersionedUpdateMixin):
    """An update that refuses to overwrite somebody else's change."""

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()  # type: ignore[attr-defined]
        self.perform_precondition_check(instance)
        self._versioned_instance = instance
        return cast("Response", super().update(request, *args, **kwargs))  # type: ignore[misc]

    def perform_update(self, serializer: Any) -> None:
        instance = serializer.instance
        concurrency.bump(instance)
        serializer.save(version=instance.version)


class ReadOnlyTenantViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantAPIView):
    """Lists and details, with every shared filter applied."""


class TenantViewSet(
    IdempotentCreateMixin,
    mixins.CreateModelMixin,
    VersionedUpdateMixin,
    mixins.UpdateModelMixin,
    ReadOnlyTenantViewSet,
):
    """The full set. `PUT` is not offered — the conventions use `PATCH` only."""

    http_method_names = ["get", "post", "patch", "head", "options"]
