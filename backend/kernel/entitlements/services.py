"""Syncing manifests into the database, installing modules, and granting features."""

from datetime import datetime
from typing import Any, cast

import structlog
from django.db import transaction

from kernel.audit import services as audit
from kernel.audit.models import AuditAction
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Tenant

from . import manifest as manifests
from . import resolver
from .models import Feature, FeatureGrant, GrantSource, Module, TenantModule

logger = structlog.get_logger(__name__)


class ModuleNotInstalledError(ValueError):
    """A module was enabled before something it depends on."""


# --------------------------------------------------------------------------- sync
@transaction.atomic
def sync_modules() -> dict[str, int]:
    """Write the code's manifests into the database so plans can reference them.

    Idempotent. Nothing is deleted: a feature that disappears from the code keeps its row, because
    removing it would cascade away the grants recording what customers actually bought. Orphans
    are reported instead.
    """
    manifests.validate_dependencies()
    declared_features: set[str] = set()

    for item in manifests.all_manifests():
        module, _ = Module.objects.update_or_create(
            code=item.code,
            defaults={
                "name": item.name_en,
                "name_ne": item.name_ne,
                "description": item.description,
                "version": item.version,
                "status": item.status.value,
                "is_core": item.is_core,
                "depends_on": list(item.depends_on),
            },
        )
        for spec in item.features:
            Feature.objects.update_or_create(
                code=spec.code,
                defaults={
                    "module": module,
                    "name": spec.name_en,
                    "name_ne": spec.name_ne,
                    "description": spec.description,
                    "kind": spec.kind.value,
                    "unit": spec.unit,
                    "default_value": spec.default,
                },
            )
            declared_features.add(spec.code)

    orphans = set(Feature.objects.values_list("code", flat=True)) - declared_features
    if orphans:
        logger.warning("entitlement_features_no_longer_declared", codes=sorted(orphans))

    resolver.invalidate_all()
    return {
        "modules": len(manifests.all_manifests()),
        "features": len(declared_features),
        "orphans": len(orphans),
    }


# --------------------------------------------------------------------------- installation
@transaction.atomic
def install_module(tenant: Tenant, code: str, *, enable: bool = True) -> list[TenantModule]:
    """Install a module and everything it depends on, dependencies first.

    Opens the tenant's own context: the control plane calls this from outside any tenant, and
    row-level security rightly refuses writes that do not name the tenant they belong to.
    """
    installed: list[TenantModule] = []
    with tenant_context(tenant.pk):
        for module_code in manifests.resolve_install_order(code):
            module = Module.objects.get(code=module_code)
            tenant_module, created = cast(
                "tuple[TenantModule, bool]",
                TenantModule.all_tenants.get_or_create(
                    tenant=tenant, module=module, defaults={"is_enabled": enable}
                ),
            )
            if created:
                logger.info("module_installed", tenant_id=str(tenant.pk), module=module_code)
            installed.append(tenant_module)
    resolver.invalidate(tenant.pk)
    return installed


def install_core_modules(tenant: Tenant) -> list[TenantModule]:
    """Everything marked always-on. Run at provisioning and after a release adds a core module."""
    installed: list[TenantModule] = []
    for code in manifests.core_codes():
        installed.extend(install_module(tenant, code))
    return installed


@transaction.atomic
def set_module_enabled(
    tenant: Tenant, code: str, *, enabled: bool, reason: str = "", actor: Any = None
) -> TenantModule:
    """Switch a module on or off. Disabling hides it; the data stays exactly where it is."""
    module = Module.objects.get(code=code)
    if module.is_core and not enabled:
        raise ValueError(f"{code} is part of the platform and cannot be switched off.")

    with tenant_context(tenant.pk):
        tenant_module = cast(
            "TenantModule", TenantModule.all_tenants.get(tenant=tenant, module=module)
        )
        was_enabled = tenant_module.is_enabled
        tenant_module.is_enabled = enabled
        tenant_module.disabled_reason = "" if enabled else reason
        tenant_module.save(update_fields=["is_enabled", "disabled_reason", "updated_at"])

        audit.record(
            action=AuditAction.SETTINGS_CHANGE,
            actor=actor,
            entity=tenant_module,
            entity_label=module.name,
            changes={"is_enabled": {"from": was_enabled, "to": enabled}},
            reason=reason,
        )

    resolver.invalidate(tenant.pk)
    return tenant_module


# --------------------------------------------------------------------------- grants
@transaction.atomic
def grant_feature(
    tenant: Tenant,
    code: str,
    *,
    value: Any = True,
    source: str = GrantSource.PLAN,
    reason: str = "",
    expires_at: datetime | None = None,
    actor: Any = None,
) -> FeatureGrant:
    feature = Feature.objects.get(code=code)
    with tenant_context(tenant.pk):
        grant, _ = cast(
            "tuple[FeatureGrant, bool]",
            FeatureGrant.all_tenants.update_or_create(
                tenant=tenant,
                feature=feature,
                source=source,
                defaults={
                    "value": value,
                    "reason": reason,
                    "expires_at": expires_at,
                    "granted_by": actor,
                },
            ),
        )
    resolver.invalidate(tenant.pk)
    return grant


@transaction.atomic
def revoke_feature(tenant: Tenant, code: str, *, source: str = GrantSource.PLAN) -> None:
    with tenant_context(tenant.pk):
        FeatureGrant.all_tenants.filter(tenant=tenant, feature__code=code, source=source).delete()
    resolver.invalidate(tenant.pk)


@transaction.atomic
def apply_plan_features(tenant: Tenant, values: dict[str, Any], *, reason: str = "") -> None:
    """Project a plan's features onto a tenant, replacing whatever the previous plan granted.

    Add-ons and overrides are left untouched: buying a plan should not silently cancel the extra
    branch a pharmacy paid for separately.
    """
    with tenant_context(tenant.pk):
        FeatureGrant.all_tenants.filter(tenant=tenant, source=GrantSource.PLAN).exclude(
            feature__code__in=list(values)
        ).delete()
    for code, value in values.items():
        grant_feature(tenant, code, value=value, source=GrantSource.PLAN, reason=reason)
    resolver.invalidate(tenant.pk)
