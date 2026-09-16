"""Limits have to hold wherever a record is created, not only where a screen creates it."""

import pytest

from kernel.entitlements import services
from kernel.entitlements.models import GrantSource
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Branch, Location
from kernel.tenancy.services import create_branch
from kernel.tenancy.tests.factories import make_tenant
from shared.errors import DomainError

pytestmark = pytest.mark.django_db

BRANCHES = "platform.branches"


@pytest.fixture
def provisioned():
    return make_tenant("alpha")


def test_a_branch_within_the_plan_is_created(provisioned):
    services.grant_feature(provisioned.tenant, BRANCHES, value=3)
    with tenant_context(provisioned.tenant.id):
        branch = create_branch(
            legal_entity=provisioned.legal_entity, code="BR2", name="Second branch"
        )
        assert Branch.objects.count() == 2
        # A new branch gets the same default locations as the first, including the cabinet.
        assert Location.objects.filter(branch=branch, code="CABINET").exists()


def test_the_plan_ceiling_is_enforced(provisioned):
    services.grant_feature(provisioned.tenant, BRANCHES, value=2)
    with tenant_context(provisioned.tenant.id):
        create_branch(legal_entity=provisioned.legal_entity, code="BR2", name="Second")
        with pytest.raises(DomainError) as caught:
            create_branch(legal_entity=provisioned.legal_entity, code="BR3", name="Third")

    assert caught.value.error.code == "FEATURE_LIMIT_REACHED"
    with tenant_context(provisioned.tenant.id):
        assert Branch.objects.count() == 2


def test_buying_an_add_on_raises_the_ceiling(provisioned):
    services.grant_feature(provisioned.tenant, BRANCHES, value=2)
    with tenant_context(provisioned.tenant.id):
        create_branch(legal_entity=provisioned.legal_entity, code="BR2", name="Second")

    services.grant_feature(
        provisioned.tenant, BRANCHES, value=1, source=GrantSource.ADDON, reason="Extra branch"
    )

    with tenant_context(provisioned.tenant.id):
        create_branch(legal_entity=provisioned.legal_entity, code="BR3", name="Third")
        assert Branch.objects.count() == 3


def test_with_no_plan_there_is_no_ceiling(provisioned):
    with tenant_context(provisioned.tenant.id):
        for number in range(2, 6):
            create_branch(
                legal_entity=provisioned.legal_entity, code=f"BR{number}", name=f"Branch {number}"
            )
        assert Branch.objects.count() == 5


def test_creating_a_branch_is_audited(provisioned):
    from kernel.audit.models import AuditAction, AuditEvent

    with tenant_context(provisioned.tenant.id):
        create_branch(legal_entity=provisioned.legal_entity, code="BR2", name="Second")
        event = AuditEvent.objects.filter(action=AuditAction.CREATE).first()

    assert event is not None
    assert event.entity_type == "tenancy.Branch"
    assert event.changes["code"]["to"] == "BR2"
