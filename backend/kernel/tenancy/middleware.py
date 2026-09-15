"""Bind the resolved tenant to the request, the database session and the logs."""

from collections.abc import Callable

import structlog
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from kernel.foundation.api.exceptions import envelope
from shared.errors import ErrorCode

from . import errors
from .context import tenant_context
from .models import Tenant
from .resolution import resolve_tenant

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

DEFAULT_EXEMPT_PREFIXES = (
    "/healthz",
    "/readyz",
    "/version",
    "/api/schema",
    "/api/docs",
    "/api/redoc",
    "/django-admin",
    "/console-api",
    "/static",
    "/media",
)


def _error_response(error: ErrorCode) -> JsonResponse:
    return JsonResponse(envelope(error, error.message_en), status=error.http_status)


class TenantMiddleware:
    """Resolve the tenant, enforce its status, and run the view inside its context.

    When no tenant resolves the request continues **without** a tenant context. Tenant-scoped
    queries then return nothing and writes raise, so an unresolved tenant fails closed rather than
    falling back to some default account.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.exempt_prefixes = tuple(
            getattr(settings, "TENANT_EXEMPT_PATH_PREFIXES", DEFAULT_EXEMPT_PREFIXES)
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path.startswith(self.exempt_prefixes):
            return self.get_response(request)

        tenant = resolve_tenant(request)
        request.tenant = tenant  # type: ignore[attr-defined]

        if tenant is None:
            return self.get_response(request)

        if not tenant.is_accessible:
            return _error_response(errors.TENANT_INACTIVE)

        if tenant.is_read_only and request.method not in SAFE_METHODS:
            # Reads, prints and exports stay available: a pharmacy must still be able to produce
            # its registers for DDA or IRD while its subscription is unpaid.
            return _error_response(errors.TENANT_READ_ONLY)

        structlog.contextvars.bind_contextvars(tenant_id=str(tenant.id), tenant_slug=tenant.slug)
        with tenant_context(tenant.id):
            return self.get_response(request)


def get_request_tenant(request: HttpRequest) -> Tenant | None:
    return getattr(request, "tenant", None)
