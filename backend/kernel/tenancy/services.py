"""Tenant lifecycle. The only supported way to create or change the state of a tenant."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog
from django.db import transaction

from .context import tenant_context
from .models import (
    Branch,
    LegalEntity,
    Location,
    LocationType,
    Tenant,
    TenantDomain,
    TenantMembership,
    TenantStatus,
)

if TYPE_CHECKING:
    from kernel.identity.models import User

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProvisionedTenant:
    tenant: Tenant
    legal_entity: LegalEntity
    branch: Branch
    created: bool


@transaction.atomic
def provision_tenant(
    *,
    slug: str,
    name: str,
    legal_name: str,
    pan: str,
    branch_name: str,
    branch_code: str = "HQ",
    is_vat_registered: bool = False,
    status: str = TenantStatus.TRIAL,
    name_ne: str = "",
    domain: str | None = None,
    owner: "User | None" = None,
) -> ProvisionedTenant:
    """Create a tenant with its first legal entity, branch and stock locations.

    Idempotent on `slug`: running it again returns the existing tenant untouched, so a retried
    provisioning job or a support agent clicking twice cannot produce a half-built second account.
    """
    tenant, created = Tenant.objects.get_or_create(
        slug=slug,
        defaults={"name": name, "name_ne": name_ne, "status": TenantStatus.PROVISIONING},
    )

    # The tenant row itself is outside row-level security; everything below is inside it.
    with tenant_context(tenant.id):
        legal_entity, _ = LegalEntity.all_tenants.get_or_create(
            tenant=tenant,
            pan=pan,
            defaults={"name": legal_name, "is_vat_registered": is_vat_registered},
        )
        branch, branch_created = Branch.all_tenants.get_or_create(
            tenant=tenant,
            code=branch_code,
            defaults={"legal_entity": legal_entity, "name": branch_name},
        )
        if branch_created:
            _create_default_locations(tenant=tenant, branch=branch)

    if domain:
        TenantDomain.objects.get_or_create(
            domain=domain.strip().lower(),
            defaults={"tenant": tenant, "is_primary": True, "is_verified": True},
        )

    if owner is not None:
        # Without a membership nobody could sign in on this tenant's own address.
        membership, _ = TenantMembership.objects.get_or_create(
            tenant=tenant, user=owner, defaults={"status": TenantMembership.Status.ACTIVE}
        )
        if membership.default_branch_id is None:
            membership.default_branch = branch
            membership.status = TenantMembership.Status.ACTIVE
            membership.save(update_fields=["default_branch", "status", "updated_at"])

    if created:
        tenant.set_status(status, reason="Provisioned")
        logger.info("tenant_provisioned", tenant_id=str(tenant.id), slug=slug)

    return ProvisionedTenant(
        tenant=tenant, legal_entity=legal_entity, branch=branch, created=created
    )


def _create_default_locations(*, tenant: Tenant, branch: Branch) -> None:
    """Every branch needs somewhere to sell from, somewhere to store, and a lockable cabinet.

    The locked cabinet exists from day one because Samuha KA (narcotic) stock may not be held
    anywhere else.
    """
    defaults = [
        ("COUNTER", "Sales counter", LocationType.COUNTER, True),
        ("STORE", "Store room", LocationType.STORE, True),
        ("CABINET", "Locked cabinet (narcotics)", LocationType.LOCKED_CABINET, True),
        ("QUARANTINE", "Quarantine", LocationType.STORE, False),
    ]
    for code, location_name, location_type, is_sellable in defaults:
        Location.all_tenants.get_or_create(
            tenant=tenant,
            branch=branch,
            code=code,
            defaults={"name": location_name, "type": location_type, "is_sellable": is_sellable},
        )


def suspend_tenant(tenant: Tenant, *, reason: str) -> Tenant:
    """Put a tenant into read-only mode. No data is deleted or hidden."""
    tenant.set_status(TenantStatus.SUSPENDED, reason=reason)
    logger.info("tenant_suspended", tenant_id=str(tenant.id), reason=reason)
    return tenant


def reactivate_tenant(tenant: Tenant, *, reason: str = "") -> Tenant:
    tenant.set_status(TenantStatus.ACTIVE, reason=reason)
    logger.info("tenant_reactivated", tenant_id=str(tenant.id))
    return tenant
