"""Helpers for building tenants in tests."""

from kernel.tenancy.models import Tenant, TenantStatus
from kernel.tenancy.services import ProvisionedTenant, provision_tenant

_PAN_SEQUENCE = iter(range(100_000_001, 100_001_000))


def make_tenant(
    slug: str = "alpha",
    *,
    name: str | None = None,
    status: str = TenantStatus.ACTIVE,
    is_vat_registered: bool = False,
    owner: object = None,
) -> ProvisionedTenant:
    """Provision a complete tenant: legal entity, branch, stock locations and system roles.

    Passing `owner` also creates their membership and grants them the Owner role.
    """
    return provision_tenant(
        slug=slug,
        name=name or slug.title() + " Pharmacy",
        legal_name=(name or slug.title()) + " Pvt. Ltd.",
        pan=str(next(_PAN_SEQUENCE)),
        branch_name=slug.title() + " Main",
        status=status,
        is_vat_registered=is_vat_registered,
        owner=owner,  # type: ignore[arg-type]
    )


def make_tenant_only(slug: str, *, status: str = TenantStatus.ACTIVE) -> Tenant:
    """A tenant row with no organisation underneath it."""
    return Tenant.objects.create(slug=slug, name=slug.title(), status=status)
