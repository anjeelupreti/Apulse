"""Reading a setting, and changing one.

Resolution walks from the narrowest scope outwards — user, branch, legal entity, tenant — and
stops at the first value anybody set. Nothing set anywhere means the default declared in code,
which *is* the platform default: a release that improves a default improves it for everybody who
never overrode it. Overriding a default centrally, for every account at once, belongs to the
control plane (Phase 3).

Cached the way entitlements are: by a version token rather than by deleting keys, so a stale
answer is never *read*. A setting that decides whether a prescription is required is not something
to serve out of a cache that might be ten minutes behind.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import structlog
from django.core.cache import cache

from kernel.tenancy.context import get_current_tenant_id, tenant_context
from shared.ids import uuid7

from .models import STORABLE_SCOPES, SettingValue
from .registry import (
    RESOLUTION_ORDER,
    Scope,
    SettingKind,
    SettingSpec,
    SettingValueError,
    coerce,
    get_spec,
    serialise,
)

logger = structlog.get_logger(__name__)

CACHE_TIMEOUT_SECONDS = 600
_VERSION_KEY = "settings:version:{tenant_id}"


# --------------------------------------------------------------------------- cache versioning
def _version(key: str) -> str:
    token = cache.get(key)
    if token is None:
        token = uuid7().hex
        cache.set(key, token, timeout=None)
    return str(token)


def invalidate(tenant_id: UUID | str) -> None:
    cache.set(_VERSION_KEY.format(tenant_id=tenant_id), uuid7().hex, timeout=None)


def _cache_key(tenant_id: Any) -> str:
    return f"settings:{tenant_id}:{_version(_VERSION_KEY.format(tenant_id=tenant_id))}"


# --------------------------------------------------------------------------- where to look
@dataclass(frozen=True, slots=True)
class Context:
    """Who and where is asking, which decides which values apply."""

    branch: Any = None
    legal_entity: Any = None
    user: Any = None

    @classmethod
    def of(cls, branch: Any = None, legal_entity: Any = None, user: Any = None) -> "Context":
        # A branch knows its own legal entity, so the caller does not have to say both.
        if legal_entity is None and branch is not None:
            legal_entity = getattr(branch, "legal_entity", None)
        return cls(branch=branch, legal_entity=legal_entity, user=user)

    def target_for(self, scope: Scope) -> str:
        if scope is Scope.BRANCH:
            return str(self.branch.pk) if self.branch is not None else ""
        if scope is Scope.LEGAL_ENTITY:
            return str(self.legal_entity.pk) if self.legal_entity is not None else ""
        if scope is Scope.USER:
            return str(self.user.pk) if getattr(self.user, "pk", None) else ""
        return ""


def _values_for_tenant(tenant_id: Any) -> dict[tuple[str, str, str], str]:
    """Every value this account has set, in one query, keyed by (key, scope, target).

    One read rather than one per scope: resolving a setting happens on the hot path of every sale,
    and five queries to answer "is rounding on" would be five too many.
    """
    # Its own tenant context, so a caller naming an account explicitly — a background job, or
    # provisioning — reads that account's values rather than being silently handed the defaults
    # because row-level security saw no bound tenant and returned nothing.
    with tenant_context(tenant_id):
        rows = SettingValue.objects.only("key", "scope", "scope_id", "value")
        return {(row.key, row.scope, row.scope_id): row.value for row in rows}


def _cached_values(tenant_id: Any) -> dict[tuple[str, str, str], str]:
    """Nothing is cached without a tenant, because there is nothing to cache: with no account
    bound, every setting resolves to the default declared in code."""
    if tenant_id is None:
        return {}
    key = _cache_key(tenant_id)
    cached = cache.get(key)
    if cached is None:
        cached = _values_for_tenant(tenant_id)
        cache.set(key, cached, timeout=CACHE_TIMEOUT_SECONDS)
    return cast("dict[tuple[str, str, str], str]", cached)


# --------------------------------------------------------------------------- reading
def get(
    key: str,
    *,
    branch: Any = None,
    legal_entity: Any = None,
    user: Any = None,
    tenant_id: UUID | str | None = None,
) -> Any:
    """The value in force here, already the right type.

    An undeclared key raises rather than returning None: a typo that silently answers "not set"
    is how a rule quietly stops being enforced.
    """
    spec = get_spec(key)
    context = Context.of(branch=branch, legal_entity=legal_entity, user=user)
    tenant_id = tenant_id if tenant_id is not None else get_current_tenant_id()
    values = _cached_values(tenant_id)

    for scope in RESOLUTION_ORDER:
        if not spec.allows(scope):
            continue
        raw = values.get((key, str(scope), context.target_for(scope)))
        if raw is None:
            continue
        try:
            return coerce(spec, raw)
        except SettingValueError:
            # A stored value the spec no longer accepts — a choice that was removed, a range that
            # tightened. Fall through to the default rather than failing a sale, and say so.
            logger.warning("setting_value_no_longer_valid", key=key, scope=str(scope), value=raw)
            continue
    return spec.default


def get_bool(key: str, **context: Any) -> bool:
    return bool(get(key, **context))


def get_int(key: str, **context: Any) -> int:
    return int(get(key, **context))


def get_decimal(key: str, **context: Any) -> Decimal:
    return Decimal(str(get(key, **context)))


def get_str(key: str, **context: Any) -> str:
    return str(get(key, **context))


@dataclass(frozen=True, slots=True)
class ResolvedSetting:
    spec: SettingSpec
    value: Any
    scope: Scope | None
    is_default: bool


def resolve(key: str, **context: Any) -> ResolvedSetting:
    """The value *and* where it came from — what a settings screen shows next to each row.

    "Inherited from the business" and "set for this branch" are different things to the person
    looking at the screen, and without this they cannot tell which they are changing.
    """
    spec = get_spec(key)
    tenant_id = context.pop("tenant_id", None)
    tenant_id = tenant_id if tenant_id is not None else get_current_tenant_id()
    where = Context.of(**context)
    values = _cached_values(tenant_id)

    for scope in RESOLUTION_ORDER:
        if not spec.allows(scope):
            continue
        raw = values.get((key, str(scope), where.target_for(scope)))
        if raw is None:
            continue
        try:
            return ResolvedSetting(
                spec=spec, value=coerce(spec, raw), scope=scope, is_default=False
            )
        except SettingValueError:
            continue
    return ResolvedSetting(spec=spec, value=spec.default, scope=None, is_default=True)


def effective(module: str | None = None, **context: Any) -> dict[str, Any]:
    """Every setting as it currently stands, for a screen or an export."""
    from .registry import all_specs, for_module

    specs = for_module(module) if module else all_specs()
    return {key: get(key, **context) for key in specs}


# --------------------------------------------------------------------------- changing
def set_value(
    key: str,
    value: Any,
    *,
    scope: Scope = Scope.TENANT,
    branch: Any = None,
    legal_entity: Any = None,
    user: Any = None,
    actor: Any = None,
    reason: str = "",
    tenant_id: UUID | str | None = None,
) -> SettingValue:
    """Set a value at one scope, and record who changed it from what."""
    from django.db import transaction

    from kernel.audit import services as audit
    from kernel.audit import tracking
    from kernel.audit.models import AuditAction

    spec = get_spec(key)
    if scope not in STORABLE_SCOPES:
        raise SettingValueError(
            f"{key} cannot be stored per {scope}. The platform default is the default declared "
            "in code; changing it for every account belongs to the control plane."
        )
    if not spec.allows(scope):
        raise SettingValueError(
            f"{key} cannot be set per {scope}; it is settable at "
            f"{', '.join(str(allowed) for allowed in spec.scopes)}"
        )

    where = Context.of(branch=branch, legal_entity=legal_entity, user=user)
    target = where.target_for(scope)
    if scope is not Scope.TENANT and not target:
        raise SettingValueError(f"Setting {key} per {scope} needs to say which one")

    tenant_id = tenant_id if tenant_id is not None else get_current_tenant_id()
    if tenant_id is None:
        raise SettingValueError(f"Setting {key} needs an account to set it for")

    stored = serialise(spec, value)

    with tenant_context(tenant_id), transaction.atomic():
        existing = SettingValue.objects.filter(key=key, scope=str(scope), scope_id=target).first()
        previous = existing.value if existing else None

        # Tracking is paused because the entry recorded below says it better: the key, the scope
        # and the reason, rather than a row's columns moving.
        with tracking.paused():
            row, _created = SettingValue.objects.update_or_create(
                key=key,
                scope=str(scope),
                scope_id=target,
                defaults={"value": stored, "reason": reason, "set_by": actor},
            )

        audit.record(
            action=AuditAction.SETTINGS_CHANGE,
            actor=actor,
            entity=row,
            entity_label=f"{key} at {scope}",
            changes={key: {"from": previous, "to": stored}},
            reason=reason,
            branch=branch,
        )

    invalidate(tenant_id)
    logger.info(
        "setting_changed",
        key=key,
        scope=str(scope),
        value=stored,
        sensitive=spec.is_sensitive,
    )
    return cast("SettingValue", row)


def clear(
    key: str,
    *,
    scope: Scope = Scope.TENANT,
    branch: Any = None,
    legal_entity: Any = None,
    user: Any = None,
    actor: Any = None,
    reason: str = "",
    tenant_id: UUID | str | None = None,
) -> bool:
    """Remove a value so the wider scope, or the declared default, applies again."""
    from kernel.audit import services as audit
    from kernel.audit import tracking
    from kernel.audit.models import AuditAction

    spec = get_spec(key)
    where = Context.of(branch=branch, legal_entity=legal_entity, user=user)
    tenant_id = tenant_id if tenant_id is not None else get_current_tenant_id()
    if tenant_id is None:
        raise SettingValueError(f"Clearing {key} needs an account to clear it for")

    with tenant_context(tenant_id), tracking.paused():
        deleted, _ = SettingValue.objects.filter(
            key=key, scope=str(scope), scope_id=where.target_for(scope)
        ).delete()

    if deleted:
        with tenant_context(tenant_id):
            audit.record(
                action=AuditAction.SETTINGS_CHANGE,
                actor=actor,
                entity_type="settings.SettingValue",
                entity_id=key,
                entity_label=f"{key} at {scope}",
                changes={key: {"from": "set", "to": f"inherited (default {spec.default})"}},
                reason=reason,
                branch=branch,
            )
    invalidate(tenant_id)
    return bool(deleted)


def kind_of(key: str) -> SettingKind:
    return get_spec(key).kind
