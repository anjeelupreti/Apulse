import pytest

from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import (
    Branch,
    LegalEntity,
    Location,
    LocationType,
    Tenant,
    TenantStatus,
)
from kernel.tenancy.services import provision_tenant, reactivate_tenant, suspend_tenant

from .factories import make_tenant

pytestmark = pytest.mark.django_db


def test_provisioning_builds_the_whole_organisation():
    result = provision_tenant(
        slug="sunrise",
        name="Sunrise Pharmacy",
        legal_name="Sunrise Pharma Pvt. Ltd.",
        pan="301234567",
        branch_name="Sunrise Main",
        is_vat_registered=True,
    )
    assert result.created
    assert result.tenant.status == TenantStatus.TRIAL
    assert result.legal_entity.is_vat_registered

    with tenant_context(result.tenant.id):
        assert LegalEntity.objects.count() == 1
        assert Branch.objects.get().code == "HQ"
        codes = set(Location.objects.values_list("code", flat=True))
    assert codes == {"COUNTER", "STORE", "CABINET", "QUARANTINE"}


def test_every_branch_gets_a_locked_cabinet():
    """Samuha KA stock may not be kept anywhere else, so the location exists from day one."""
    result = make_tenant("alpha")
    with tenant_context(result.tenant.id):
        cabinet = Location.objects.get(code="CABINET")
    assert cabinet.type == LocationType.LOCKED_CABINET


def test_quarantine_location_is_not_sellable():
    result = make_tenant("alpha")
    with tenant_context(result.tenant.id):
        assert Location.objects.get(code="QUARANTINE").is_sellable is False


def test_provisioning_is_idempotent():
    """A retried provisioning job must not build a second half-finished account."""
    first = provision_tenant(
        slug="sunrise",
        name="Sunrise Pharmacy",
        legal_name="Sunrise Pharma Pvt. Ltd.",
        pan="301234567",
        branch_name="Sunrise Main",
    )
    second = provision_tenant(
        slug="sunrise",
        name="Sunrise Pharmacy",
        legal_name="Sunrise Pharma Pvt. Ltd.",
        pan="301234567",
        branch_name="Sunrise Main",
    )
    assert first.tenant.id == second.tenant.id
    assert not second.created
    assert Tenant.objects.filter(slug="sunrise").count() == 1
    with tenant_context(first.tenant.id):
        assert Branch.objects.count() == 1
        assert Location.objects.count() == 4


def test_provisioning_registers_a_primary_domain():
    result = provision_tenant(
        slug="sunrise",
        name="Sunrise Pharmacy",
        legal_name="Sunrise Pharma Pvt. Ltd.",
        pan="301234567",
        branch_name="Sunrise Main",
        domain="Sunrise.Com.NP",
    )
    domain = result.tenant.domains.get()
    assert domain.domain == "sunrise.com.np"  # normalised
    assert domain.is_primary


def test_suspend_and_reactivate_record_the_reason():
    tenant = make_tenant("alpha").tenant

    suspend_tenant(tenant, reason="Invoice 42 unpaid")
    tenant.refresh_from_db()
    assert tenant.is_read_only
    assert tenant.is_accessible  # still able to sign in and read
    assert tenant.status_reason == "Invoice 42 unpaid"

    reactivate_tenant(tenant, reason="Paid")
    tenant.refresh_from_db()
    assert tenant.status == TenantStatus.ACTIVE
    assert not tenant.is_read_only


def test_suspension_never_removes_data():
    result = make_tenant("alpha")
    suspend_tenant(result.tenant, reason="unpaid")
    with tenant_context(result.tenant.id):
        assert Branch.objects.count() == 1
        assert Location.objects.count() == 4
