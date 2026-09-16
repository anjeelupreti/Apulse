"""Access changes must leave a trail — it is one of the first things an inspection asks about."""

import pytest

from kernel.audit.models import AuditAction, AuditEvent
from kernel.identity.models import User
from kernel.rbac import system_roles
from kernel.rbac.models import Role
from kernel.rbac.services import assign_role, clone_role, revoke_role, set_role_permissions
from kernel.tenancy.context import tenant_context
from kernel.tenancy.tests.factories import make_tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return make_tenant("alpha")


@pytest.fixture
def user():
    return User.objects.create_user("ram@example.com", "password-1234", full_name="Ram Sharma")


@pytest.fixture
def owner():
    return User.objects.create_user("owner@example.com", "password-1234", full_name="Owner")


def test_granting_a_role_is_recorded(tenant, user, owner):
    with tenant_context(tenant.tenant.id):
        assign_role(
            user=user,
            role=Role.objects.get(code=system_roles.PHARMACIST),
            granted_by=owner,
            reason="New hire",
        )
        event = AuditEvent.objects.filter(action=AuditAction.PERMISSION_CHANGE).first()

    assert event is not None
    assert event.actor_label == "Owner"
    assert event.entity_label == "Ram Sharma as Pharmacist"
    assert event.changes["granted"]["to"] == system_roles.PHARMACIST
    assert event.reason == "New hire"


def test_revoking_a_role_is_recorded(tenant, user, owner):
    with tenant_context(tenant.tenant.id):
        assignment = assign_role(user=user, role=Role.objects.get(code=system_roles.PHARMACIST))
        revoke_role(assignment, actor=owner, reason="Left the pharmacy")

        event = AuditEvent.objects.order_by("-sequence").first()

    assert event is not None
    assert event.changes["granted"] == {"from": system_roles.PHARMACIST, "to": None}
    assert event.reason == "Left the pharmacy"


def test_changing_what_a_role_can_do_is_recorded(tenant):
    with tenant_context(tenant.tenant.id):
        clone = clone_role(
            Role.objects.get(code=system_roles.COUNTER_STAFF),
            code="counter_evening",
            name="Counter (evening)",
        )
        set_role_permissions(clone, ("tenancy.branch.view", "tenancy.branch.manage"))
        event = AuditEvent.objects.order_by("-sequence").first()

    assert event is not None
    assert event.action == AuditAction.PERMISSION_CHANGE
    assert "tenancy.branch.manage" in event.changes["permissions"]["to"]
    assert "tenancy.branch.manage" not in event.changes["permissions"]["from"]


def test_the_trail_stays_verifiable_after_several_changes(tenant, user, owner):
    from kernel.audit.services import verify_chain

    with tenant_context(tenant.tenant.id):
        first = assign_role(user=user, role=Role.objects.get(code=system_roles.PHARMACIST))
        assign_role(user=owner, role=Role.objects.get(code=system_roles.ACCOUNTANT))
        revoke_role(first, actor=owner)
        assert verify_chain().is_intact
