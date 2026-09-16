from datetime import timedelta

import pytest
from django.utils import timezone

from kernel.entitlements import resolver, services
from kernel.entitlements.models import FeatureFlag, GrantSource
from kernel.tenancy.context import tenant_context
from kernel.tenancy.tests.factories import make_tenant
from shared.errors import DomainError

pytestmark = pytest.mark.django_db

BRANCHES = "platform.branches"
CUSTOM_DOMAIN = "platform.custom_domain"


@pytest.fixture
def tenant():
    return make_tenant("alpha").tenant


def test_core_modules_are_installed_when_an_account_is_created(tenant):
    with tenant_context(tenant.id):
        assert resolver.current().has_module("platform")


def test_defaults_apply_when_no_plan_has_granted_anything(tenant):
    with tenant_context(tenant.id):
        entitlements = resolver.current()
        # A ceiling defaults to unlimited: restrictions arrive from a plan, they are not assumed.
        assert entitlements.limit(BRANCHES) is None
        # A switch defaults to off.
        assert entitlements.has(CUSTOM_DOMAIN) is False


def test_a_plan_grant_sets_the_value(tenant):
    services.grant_feature(tenant, BRANCHES, value=3, source=GrantSource.PLAN)
    services.grant_feature(tenant, CUSTOM_DOMAIN, value=True, source=GrantSource.PLAN)
    with tenant_context(tenant.id):
        assert resolver.current().limit(BRANCHES) == 3
        assert resolver.current().has(CUSTOM_DOMAIN)


def test_an_add_on_adds_to_what_the_plan_includes(tenant):
    """Buying two extra branches means five, not two."""
    services.grant_feature(tenant, BRANCHES, value=3, source=GrantSource.PLAN)
    services.grant_feature(tenant, BRANCHES, value=2, source=GrantSource.ADDON)
    with tenant_context(tenant.id):
        assert resolver.current().limit(BRANCHES) == 5


def test_an_override_replaces_the_result_outright(tenant):
    services.grant_feature(tenant, BRANCHES, value=3, source=GrantSource.PLAN)
    services.grant_feature(tenant, BRANCHES, value=2, source=GrantSource.ADDON)
    services.grant_feature(
        tenant, BRANCHES, value=1, source=GrantSource.OVERRIDE, reason="Billing dispute"
    )
    with tenant_context(tenant.id):
        assert resolver.current().limit(BRANCHES) == 1


def test_an_expired_grant_stops_counting(tenant):
    services.grant_feature(
        tenant,
        CUSTOM_DOMAIN,
        value=True,
        source=GrantSource.OVERRIDE,
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    with tenant_context(tenant.id):
        assert resolver.current().has(CUSTOM_DOMAIN) is False


def test_an_unexpired_grant_still_counts(tenant):
    services.grant_feature(
        tenant,
        CUSTOM_DOMAIN,
        value=True,
        source=GrantSource.OVERRIDE,
        expires_at=timezone.now() + timedelta(days=1),
    )
    with tenant_context(tenant.id):
        assert resolver.current().has(CUSTOM_DOMAIN)


def test_a_kill_switch_turns_a_feature_off_for_everyone(tenant):
    services.grant_feature(tenant, CUSTOM_DOMAIN, value=True)
    with tenant_context(tenant.id):
        assert resolver.current().has(CUSTOM_DOMAIN)

    FeatureFlag.objects.create(feature_code=CUSTOM_DOMAIN, is_killed=True)
    resolver.invalidate_all()

    with tenant_context(tenant.id):
        assert resolver.current().has(CUSTOM_DOMAIN) is False


def test_a_rollout_that_excludes_an_account_hides_the_feature(tenant):
    services.grant_feature(tenant, CUSTOM_DOMAIN, value=True)
    FeatureFlag.objects.create(feature_code=CUSTOM_DOMAIN, rollout_percent=0)
    resolver.invalidate_all()
    with tenant_context(tenant.id):
        assert resolver.current().has(CUSTOM_DOMAIN) is False


def test_disabling_a_module_hides_its_features_without_losing_the_grants(
    tenant, temporary_manifests
):
    """A downgrade must never delete what a pharmacy recorded."""
    from kernel.entitlements.manifest import FeatureSpec, ModuleManifest, register

    register(
        ModuleManifest(
            code="wholesale",
            name_en="Wholesale",
            name_ne="थोक",
            description="Distribution",
            features=(
                FeatureSpec(code="wholesale.routes", name_en="Delivery routes", name_ne="मार्ग"),
            ),
        )
    )
    services.sync_modules()
    services.install_module(tenant, "wholesale")
    services.grant_feature(tenant, "wholesale.routes", value=True)

    with tenant_context(tenant.id):
        assert resolver.current().has("wholesale.routes")

    services.set_module_enabled(tenant, "wholesale", enabled=False, reason="Downgraded plan")
    with tenant_context(tenant.id):
        entitlements = resolver.current()
        assert not entitlements.has_module("wholesale")
        assert "wholesale.routes" not in entitlements.features

    services.set_module_enabled(tenant, "wholesale", enabled=True)
    with tenant_context(tenant.id):
        assert resolver.current().has("wholesale.routes")  # the grant was waiting all along


def test_accounts_do_not_share_entitlements():
    first = make_tenant("alpha").tenant
    second = make_tenant("bravo").tenant
    services.grant_feature(first, CUSTOM_DOMAIN, value=True)

    with tenant_context(first.id):
        assert resolver.current().has(CUSTOM_DOMAIN)
    with tenant_context(second.id):
        assert resolver.current().has(CUSTOM_DOMAIN) is False


# --------------------------------------------------------------------------- caching
def test_a_grant_takes_effect_immediately(tenant):
    """The cache must never be the reason an account is refused something it just bought."""
    with tenant_context(tenant.id):
        assert resolver.current().has(CUSTOM_DOMAIN) is False

    services.grant_feature(tenant, CUSTOM_DOMAIN, value=True)

    with tenant_context(tenant.id):
        assert resolver.current().has(CUSTOM_DOMAIN)


def test_revoking_takes_effect_immediately(tenant):
    services.grant_feature(tenant, CUSTOM_DOMAIN, value=True)
    with tenant_context(tenant.id):
        assert resolver.current().has(CUSTOM_DOMAIN)

    services.revoke_feature(tenant, CUSTOM_DOMAIN)
    with tenant_context(tenant.id):
        assert resolver.current().has(CUSTOM_DOMAIN) is False


def test_the_cached_answer_matches_a_fresh_one(tenant):
    services.grant_feature(tenant, BRANCHES, value=4)
    with tenant_context(tenant.id):
        cached = resolver.current()
        fresh = resolver.resolve(tenant.id)
    assert cached.as_dict() == fresh.as_dict()


# --------------------------------------------------------------------------- enforcement
def test_requiring_a_feature_refuses_with_a_useful_message(tenant):
    with tenant_context(tenant.id), pytest.raises(DomainError) as caught:
        resolver.require_feature(CUSTOM_DOMAIN)
    assert caught.value.error.code == "FEATURE_NOT_ENTITLED"
    assert caught.value.error.message_ne


def test_requiring_a_granted_feature_passes(tenant):
    services.grant_feature(tenant, CUSTOM_DOMAIN, value=True)
    with tenant_context(tenant.id):
        resolver.require_feature(CUSTOM_DOMAIN)


def test_capacity_is_refused_at_the_ceiling(tenant):
    services.grant_feature(tenant, BRANCHES, value=2)
    with tenant_context(tenant.id):
        resolver.require_capacity(BRANCHES, used=1)
        with pytest.raises(DomainError) as caught:
            resolver.require_capacity(BRANCHES, used=2)

    assert caught.value.error.code == "FEATURE_LIMIT_REACHED"
    # The message names the ceiling rather than just refusing.
    assert "2 branches" in caught.value.message


def test_an_unlimited_ceiling_never_refuses(tenant):
    with tenant_context(tenant.id):
        resolver.require_capacity(BRANCHES, used=10_000)


def test_remaining_capacity_is_reported(tenant):
    services.grant_feature(tenant, BRANCHES, value=5)
    with tenant_context(tenant.id):
        assert resolver.remaining(BRANCHES, used=3) == 2
        assert resolver.remaining(BRANCHES, used=9) == 0
