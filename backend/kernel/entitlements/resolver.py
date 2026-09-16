"""Working out what an account may actually use, and caching the answer safely."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from kernel.tenancy.context import (
    get_current_tenant_id,
    require_current_tenant_id,
    tenant_context,
)
from shared.errors import DomainError
from shared.ids import uuid7

from . import errors, flags
from .manifest import FeatureKind
from .models import Feature, FeatureGrant, GrantSource, TenantModule

CACHE_TIMEOUT_SECONDS = 600
_TENANT_VERSION_KEY = "entitlements:version:{tenant_id}"
_GLOBAL_VERSION_KEY = "entitlements:version:global"


# --------------------------------------------------------------------------- cache versioning
def _version(key: str) -> str:
    """A token that changes whenever the underlying data does.

    Versioning rather than deleting keys means a stale entry is never *read*, only left to expire.
    A stale entitlement would either sell something that was not bought or refuse something that
    was, so correctness here is worth more than a cache hit.
    """
    token = cache.get(key)
    if token is None:
        token = uuid7().hex
        cache.set(key, token, timeout=None)
    return str(token)


def _bump(key: str) -> None:
    cache.set(key, uuid7().hex, timeout=None)


def invalidate(tenant_id: UUID | str) -> None:
    _bump(_TENANT_VERSION_KEY.format(tenant_id=tenant_id))


def invalidate_all() -> None:
    """After a change that affects every account, such as a kill switch."""
    _bump(_GLOBAL_VERSION_KEY)


def _cache_key(tenant_id: UUID | str) -> str:
    tenant_version = _version(_TENANT_VERSION_KEY.format(tenant_id=tenant_id))
    global_version = _version(_GLOBAL_VERSION_KEY)
    return f"entitlements:{tenant_id}:{tenant_version}:{global_version}"


# --------------------------------------------------------------------------- the answer
@dataclass(frozen=True, slots=True)
class Entitlements:
    tenant_id: str
    modules: frozenset[str]
    features: dict[str, Any]

    def has_module(self, code: str) -> bool:
        return code in self.modules

    def has(self, code: str) -> bool:
        """True for a switch that is on, or a ceiling that is anything other than zero."""
        value = self.features.get(code)
        if isinstance(value, bool):
            return value
        if value is None:
            return code in self.features  # an unlimited ceiling is still an entitlement
        return bool(value)

    def limit(self, code: str) -> int | None:
        """The ceiling, or None for unlimited."""
        value = self.features.get(code)
        return None if value is None or isinstance(value, bool) else int(value)

    def as_dict(self) -> dict[str, Any]:
        return {"modules": sorted(self.modules), "features": dict(sorted(self.features.items()))}


def resolve(tenant_id: UUID | str) -> Entitlements:
    """Compute from the database, ignoring the cache.

    Enters the tenant's own context so this is equally correct when the control plane asks about
    an account it is not currently serving; row-level security would otherwise return nothing.
    """
    with tenant_context(tenant_id):
        return _resolve_in_context(tenant_id)


def _resolve_in_context(tenant_id: UUID | str) -> Entitlements:
    enabled_modules = {
        tenant_module.module.code
        for tenant_module in TenantModule.all_tenants.filter(
            tenant_id=tenant_id, is_enabled=True
        ).select_related("module")
    }

    features = {
        feature.code: feature
        for feature in Feature.objects.select_related("module")
        if feature.module.code in enabled_modules
    }

    resolved: dict[str, Any] = {code: feature.default_value for code, feature in features.items()}

    now = timezone.now()
    grants = (
        FeatureGrant.all_tenants.filter(tenant_id=tenant_id)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .select_related("feature")
    )

    plan_values: dict[str, Any] = {}
    addon_totals: dict[str, Any] = {}
    overrides: dict[str, Any] = {}
    for grant in grants:
        code = grant.feature.code
        if code not in features:
            continue  # the module is not enabled, so the grant is dormant rather than gone
        if grant.source == GrantSource.PLAN:
            plan_values[code] = grant.value
        elif grant.source == GrantSource.ADDON:
            # First add-on sets the running total; later ones combine with it. Seeding from an
            # absent key would look like "unlimited" and swallow the value.
            addon_totals[code] = (
                _combine(features[code].kind, addon_totals[code], grant.value)
                if code in addon_totals
                else grant.value
            )
        else:
            overrides[code] = grant.value

    for code, feature in features.items():
        if code in overrides:
            resolved[code] = overrides[code]
            continue
        base = plan_values.get(code, feature.default_value)
        if code in addon_totals:
            base = _combine(feature.kind, base, addon_totals[code])
        resolved[code] = base

    flag_map = flags.flags_by_code()
    for code in list(resolved):
        flag = flag_map.get(code)
        if flag is not None and not flags.flag_allows(flag, tenant_id):
            resolved[code] = False if features[code].kind == FeatureKind.BOOLEAN else 0

    return Entitlements(
        tenant_id=str(tenant_id), modules=frozenset(enabled_modules), features=resolved
    )


def _combine(kind: str, first: Any, second: Any) -> Any:
    """Add ceilings together; OR switches. An extra-branch add-on adds to what the plan includes."""
    if kind == FeatureKind.BOOLEAN:
        return bool(first) or bool(second)
    if first is None or second is None:
        return None  # unlimited on either side stays unlimited
    return int(first) + int(second)


def for_tenant(tenant_id: UUID | str) -> Entitlements:
    key = _cache_key(tenant_id)
    cached = cache.get(key)
    if cached is not None:
        return Entitlements(
            tenant_id=str(tenant_id),
            modules=frozenset(cached["modules"]),
            features=cached["features"],
        )
    entitlements = resolve(tenant_id)
    cache.set(
        key,
        {"modules": sorted(entitlements.modules), "features": entitlements.features},
        timeout=CACHE_TIMEOUT_SECONDS,
    )
    return entitlements


def current() -> Entitlements:
    """Entitlements for the tenant this request is for."""
    return for_tenant(require_current_tenant_id())


def current_or_none() -> Entitlements | None:
    tenant_id = get_current_tenant_id()
    return for_tenant(tenant_id) if tenant_id else None


# --------------------------------------------------------------------------- enforcement
def has_feature(code: str) -> bool:
    return current().has(code)


def require_module(code: str) -> None:
    if not current().has_module(code):
        raise DomainError(errors.MODULE_NOT_ENABLED)


def require_feature(code: str) -> None:
    if not current().has(code):
        raise DomainError(errors.FEATURE_NOT_ENTITLED)


def remaining(code: str, used: int) -> int | None:
    """How many more are allowed, or None for unlimited."""
    limit = current().limit(code)
    return None if limit is None else max(limit - used, 0)


def require_capacity(code: str, used: int, *, adding: int = 1) -> None:
    """Refuse to go past a ceiling, naming the ceiling rather than just saying no."""
    entitlements = current()
    limit = entitlements.limit(code)
    if limit is None:
        return
    if used + adding > limit:
        feature = Feature.objects.filter(code=code).first()
        label = feature.name.lower() if feature else code
        raise DomainError(
            errors.FEATURE_LIMIT_REACHED,
            f"Your plan includes {limit} {label}. Upgrade to add more.",
        )
