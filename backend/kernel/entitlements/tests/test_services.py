import pytest

from kernel.entitlements import manifest, resolver, services
from kernel.entitlements.manifest import ModuleManifest, register
from kernel.entitlements.models import Feature, FeatureGrant, GrantSource, Module, TenantModule
from kernel.tenancy.context import tenant_context
from kernel.tenancy.tests.factories import make_tenant

pytestmark = pytest.mark.django_db

BRANCHES = "platform.branches"
CUSTOM_DOMAIN = "platform.custom_domain"


@pytest.fixture
def tenant():
    return make_tenant("alpha").tenant


def test_sync_writes_the_declared_modules_and_features():
    services.sync_modules()
    platform = Module.objects.get(code="platform")
    assert platform.is_core
    assert set(platform.features.values_list("code", flat=True)) == {
        spec.code for spec in manifest.get("platform").features
    }


def test_sync_is_idempotent():
    services.sync_modules()
    before = (Module.objects.count(), Feature.objects.count())
    services.sync_modules()
    assert (Module.objects.count(), Feature.objects.count()) == before


def test_sync_keeps_features_that_the_code_no_longer_declares(temporary_manifests, caplog):
    """Deleting them would cascade away the grants recording what customers bought."""
    Feature.objects.create(
        module=Module.objects.get(code="platform"),
        code="platform.retired_feature",
        name="Retired",
    )
    result = services.sync_modules()
    assert result["orphans"] == 1
    assert Feature.objects.filter(code="platform.retired_feature").exists()


def test_installing_a_module_installs_what_it_depends_on(tenant, temporary_manifests):
    register(
        ModuleManifest(
            code="wholesale",
            name_en="Wholesale",
            name_ne="थोक",
            description="Distribution",
            depends_on=("platform",),
        )
    )
    services.sync_modules()
    installed = services.install_module(tenant, "wholesale")

    codes = [tenant_module.module.code for tenant_module in installed]
    assert codes == ["platform", "wholesale"]  # dependency first


def test_installing_twice_changes_nothing(tenant):
    services.install_module(tenant, "platform")
    services.install_module(tenant, "platform")
    with tenant_context(tenant.id):
        assert TenantModule.objects.filter(module__code="platform").count() == 1


def test_a_core_module_cannot_be_switched_off(tenant):
    with pytest.raises(ValueError, match="part of the platform"):
        services.set_module_enabled(tenant, "platform", enabled=False, reason="testing")


def test_switching_a_module_off_is_recorded(tenant, temporary_manifests):
    from kernel.audit.models import AuditAction, AuditEvent

    register(
        ModuleManifest(
            code="wholesale", name_en="Wholesale", name_ne="थोक", description="Distribution"
        )
    )
    services.sync_modules()
    services.install_module(tenant, "wholesale")
    services.set_module_enabled(tenant, "wholesale", enabled=False, reason="Downgraded plan")

    with tenant_context(tenant.id):
        event = AuditEvent.objects.filter(action=AuditAction.SETTINGS_CHANGE).first()
    assert event is not None
    assert event.changes["is_enabled"] == {"from": True, "to": False}
    assert event.reason == "Downgraded plan"


def test_applying_a_plan_replaces_the_previous_plan_grants(tenant):
    services.apply_plan_features(tenant, {BRANCHES: 3, CUSTOM_DOMAIN: True}, reason="Professional")
    services.apply_plan_features(tenant, {BRANCHES: 1}, reason="Downgraded to Starter")

    with tenant_context(tenant.id):
        entitlements = resolver.current()
    assert entitlements.limit(BRANCHES) == 1
    assert entitlements.has(CUSTOM_DOMAIN) is False


def test_applying_a_plan_leaves_paid_add_ons_alone(tenant):
    """Changing plan must not silently cancel the extra branch a pharmacy bought separately."""
    services.grant_feature(tenant, BRANCHES, value=2, source=GrantSource.ADDON, reason="Extra")
    services.apply_plan_features(tenant, {BRANCHES: 3}, reason="Professional")

    with tenant_context(tenant.id):
        assert resolver.current().limit(BRANCHES) == 5
        # Inside the tenant's context: row-level security hides these rows from outside it.
        assert FeatureGrant.all_tenants.filter(tenant=tenant, source=GrantSource.ADDON).exists()
