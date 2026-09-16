from datetime import timedelta

import pytest
from django.utils import timezone

from kernel.identity.models import User
from kernel.rbac import registry, system_roles
from kernel.rbac.models import AssignmentScope, Role, RoleAssignment, RolePermission
from kernel.rbac.services import (
    UnknownPermissionError,
    assign_role,
    clone_role,
    create_role,
    revoke_role,
    set_role_permissions,
    sync_system_roles,
)
from kernel.tenancy.context import tenant_context
from kernel.tenancy.tests.factories import make_tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return make_tenant("alpha")


@pytest.fixture
def user():
    return User.objects.create_user("ram@example.com", "password-1234", full_name="Ram")


def test_provisioning_seeds_every_built_in_role(tenant):
    with tenant_context(tenant.tenant.id):
        assert Role.objects.filter(is_system=True).count() == len(system_roles.SYSTEM_ROLES)
        owner = Role.objects.get(code=system_roles.OWNER)
        assert owner.permission_codes == set(registry.all_codes())


def test_syncing_again_changes_nothing(tenant):
    with tenant_context(tenant.tenant.id):
        before = RolePermission.objects.count()
        sync_system_roles(tenant.tenant)
        assert RolePermission.objects.count() == before


def test_sync_adds_permissions_that_a_release_introduced(tenant, monkeypatch):
    with tenant_context(tenant.tenant.id):
        counter = Role.objects.get(code=system_roles.COUNTER_STAFF)
        RolePermission.objects.filter(role=counter).delete()
        assert counter.permission_codes == set()

        sync_system_roles(tenant.tenant)
        assert counter.permission_codes == set(
            system_roles.BY_CODE[system_roles.COUNTER_STAFF].resolve()
        )


def test_built_in_roles_cannot_be_edited(tenant):
    """They are kept in step with the code, so local edits would be lost on the next release."""
    with tenant_context(tenant.tenant.id):
        owner = Role.objects.get(code=system_roles.OWNER)
        with pytest.raises(ValueError, match="built-in role"):
            set_role_permissions(owner, ("tenancy.branch.view",))


def test_a_built_in_role_can_be_cloned_and_then_adjusted(tenant):
    with tenant_context(tenant.tenant.id):
        source = Role.objects.get(code=system_roles.COUNTER_STAFF)
        clone = clone_role(source, code="counter_staff_evening", name="Counter staff (evening)")
        assert clone.permission_codes == source.permission_codes
        assert not clone.is_system

        set_role_permissions(clone, ("tenancy.branch.view",))
        assert clone.permission_codes == {"tenancy.branch.view"}
        assert source.permission_codes != {"tenancy.branch.view"}


def test_a_role_cannot_grant_a_permission_nothing_checks(tenant):
    with (
        tenant_context(tenant.tenant.id),
        pytest.raises(UnknownPermissionError, match="Nothing in the codebase"),
    ):
        create_role(code="made_up", name="Made up", permissions=("pharmacy.invented.action",))


def test_assignment_scope_must_match_its_target(tenant, user):
    with tenant_context(tenant.tenant.id):
        role = Role.objects.get(code=system_roles.PHARMACIST)
        with pytest.raises(ValueError, match="needs a branch"):
            assign_role(user=user, role=role, scope=AssignmentScope.BRANCH)
        with pytest.raises(ValueError, match="must not name a branch"):
            assign_role(
                user=user,
                role=role,
                scope=AssignmentScope.TENANT,
                branch=tenant.branch,
            )


def test_assigning_the_same_role_twice_updates_rather_than_duplicates(tenant, user):
    with tenant_context(tenant.tenant.id):
        role = Role.objects.get(code=system_roles.PHARMACIST)
        expiry = timezone.now() + timedelta(days=7)
        assign_role(user=user, role=role, reason="first")
        assign_role(user=user, role=role, expires_at=expiry, reason="locum cover")

        assignment = RoleAssignment.objects.get(user=user, role=role)
        assert assignment.reason == "locum cover"
        assert assignment.expires_at == expiry


def test_revoking_removes_the_assignment(tenant, user):
    with tenant_context(tenant.tenant.id):
        role = Role.objects.get(code=system_roles.PHARMACIST)
        assignment = assign_role(user=user, role=role)
        revoke_role(assignment)
        assert not RoleAssignment.objects.filter(user=user).exists()


def test_the_owner_of_a_new_account_can_actually_use_it(user):
    """A freshly provisioned account whose owner held no role would be unusable."""
    provisioned = make_tenant("sunrise", owner=user)
    with tenant_context(provisioned.tenant.id):
        assignment = RoleAssignment.objects.get(user=user)
        assert assignment.role.code == system_roles.OWNER
        assert assignment.scope == AssignmentScope.TENANT
