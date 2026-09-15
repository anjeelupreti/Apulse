"""Work out which tenant a request belongs to."""

from django.conf import settings
from django.http import HttpRequest

from .models import Tenant, TenantDomain

TENANT_HEADER = "X-Tenant"


def _base_domain() -> str:
    return getattr(settings, "TENANT_BASE_DOMAIN", "").strip().lower()


def slug_from_host(host: str) -> str | None:
    """`acme.app.example.com` → `acme`, given TENANT_BASE_DOMAIN `app.example.com`."""
    base = _base_domain()
    if not base or host == base or not host.endswith("." + base):
        return None
    slug = host[: -(len(base) + 1)]
    return slug if slug and "." not in slug else None


def resolve_tenant(request: HttpRequest) -> Tenant | None:
    """Resolve by custom domain, then by subdomain, then (only if enabled) by header.

    Deliberately not cached yet: a cached row would keep serving a suspended or cancelled tenant
    as writable until the entry expired. Caching comes with explicit invalidation on status change.
    """
    host = request.get_host().split(":")[0].lower()

    domain = (
        TenantDomain.objects.select_related("tenant").filter(domain=host, is_verified=True).first()
    )
    if domain is not None:
        return domain.tenant

    slug = slug_from_host(host)
    if slug:
        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is not None:
            return tenant

    # Header resolution is for token clients (desktop POS, mobile). It is off by default because
    # on its own it lets any caller name any tenant; M2.2 enables it once the token carries the
    # tenant claim and the membership is checked.
    if getattr(settings, "TENANT_ALLOW_HEADER_RESOLUTION", False):
        header_slug = request.headers.get(TENANT_HEADER, "").strip().lower()
        if header_slug:
            return Tenant.objects.filter(slug=header_slug).first()

    return None
