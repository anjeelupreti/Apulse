from datetime import timedelta

import pytest
from django.utils import timezone

from kernel.identity.models import (
    CredentialStatus,
    CredentialType,
    User,
    UserCredential,
)
from kernel.rbac import registry, resolver, system_roles
from kernel.rbac.models import AssignmentScope, Role
from kernel.rbac.registry import Permission
from kernel.rbac.services import assign_role
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Branch
from kernel.tenancy.tests.factories import make_tenant

pytestmark = pytest.mark.django_db

GATED_CODE = "tenancy.branch.manage"


@pytest.fixture
def tenant():
    return make_tenant("alpha")


@pytest.fixture
def user():
    return User.objects.create_user("ram@example.com", "password-1234", full_name="Ram")


def role(code: str) -> Role:
    return Role.objects.get(code=code)


def test_a_user_with_no_role_has_no_permissions(tenant, user):
    with tenant_context(tenant.tenant.id):
        assert resolver.permissions_for(user) == frozenset()
        assert not resolver.has_permission(user, "tenancy.branch.view")


def test_permissions_come_from_assigned_roles(tenant, user):
    with tenant_context(tenant.tenant.id):
        assign_role(user=user, role=role(system_roles.ADMINISTRATOR))
        assert resolver.has_permission(user, "tenancy.branch.manage")
        assert not resolver.has_permission(user, "tenancy.legal_entity.manage")


def test_permissions_accumulate_across_roles(tenant, user):
    with tenant_context(tenant.tenant.id):
        assign_role(user=user, role=role(system_roles.ACCOUNTANT))
        assign_role(
            user=user,
            role=role(system_roles.STORE_KEEPER),
            scope=AssignmentScope.BRANCH,
            branch=tenant.branch,
        )
        held = resolver.permissions_for(user)
        assert "tenancy.legal_entity.view" in held
        assert "tenancy.location.manage" in held


def test_an_expired_assignment_grants_nothing(tenant, user):
    """A DDA inspector's access ends when their visit does."""
    with tenant_context(tenant.tenant.id):
        assign_role(
            user=user,
            role=role(system_roles.DDA_INSPECTOR),
            expires_at=timezone.now() - timedelta(minutes=1),
            reason="Inspection on 2026-09-15",
        )
        assert resolver.permissions_for(user) == frozenset()


def test_an_unexpired_assignment_still_grants(tenant, user):
    with tenant_context(tenant.tenant.id):
        assign_role(
            user=user,
            role=role(system_roles.DDA_INSPECTOR),
            expires_at=timezone.now() + timedelta(hours=2),
        )
        assert "tenancy.branch.view" in resolver.permissions_for(user)


def test_a_deactivated_role_grants_nothing(tenant, user):
    with tenant_context(tenant.tenant.id):
        auditor = role(system_roles.AUDITOR)
        assign_role(user=user, role=auditor)
        auditor.is_active = False
        auditor.save(update_fields=["is_active"])
        assert resolver.permissions_for(user) == frozenset()


# --------------------------------------------------------------------------- branch scope
def test_branch_scoped_role_applies_only_in_that_branch(tenant, user):
    with tenant_context(tenant.tenant.id):
        other = Branch.objects.create(
            legal_entity=tenant.legal_entity, code="BR2", name="Second branch"
        )
        assign_role(
            user=user,
            role=role(system_roles.STORE_KEEPER),
            scope=AssignmentScope.BRANCH,
            branch=tenant.branch,
        )

        assert resolver.has_permission(user, "tenancy.location.manage", branch_id=tenant.branch.id)
        assert not resolver.has_permission(user, "tenancy.location.manage", branch_id=other.id)


def test_an_account_wide_role_is_not_limited_to_branches(tenant, user):
    with tenant_context(tenant.tenant.id):
        assign_role(user=user, role=role(system_roles.ADMINISTRATOR))
        assert resolver.branch_ids_for(user, "tenancy.branch.manage") is None
        assert resolver.has_permission(user, "tenancy.branch.manage", branch_id=tenant.branch.id)


# --------------------------------------------------------------------------- credential gating
@pytest.fixture
def gated_permission(monkeypatch):
    """Treat an existing permission as one that requires pharmacist registration."""
    gated = Permission(
        code=GATED_CODE,
        label_en="Gated",
        label_ne="रोकिएको",
        requires_credential=CredentialType.PHARMACY_COUNCIL,
    )
    original = registry.get

    def patched(code: str) -> Permission:
        return gated if code == GATED_CODE else original(code)

    monkeypatch.setattr(resolver.registry, "get", patched)
    return gated


def test_a_role_alone_cannot_grant_an_action_that_needs_registration(
    tenant, user, gated_permission
):
    """No amount of role configuration makes an unregistered person a pharmacist."""
    with tenant_context(tenant.tenant.id):
        assign_role(user=user, role=role(system_roles.OWNER))
        assert GATED_CODE in resolver.permissions_for(user)
        assert not resolver.has_permission(user, GATED_CODE)


def test_a_verified_registration_unlocks_it(tenant, user, gated_permission):
    UserCredential.objects.create(
        user=user,
        type=CredentialType.PHARMACY_COUNCIL,
        registration_number="A-1234",
        status=CredentialStatus.VERIFIED,
    )
    with tenant_context(tenant.tenant.id):
        assign_role(user=user, role=role(system_roles.OWNER))
        assert resolver.has_permission(user, GATED_CODE)


def test_an_unverified_registration_does_not_count(tenant, user, gated_permission):
    UserCredential.objects.create(
        user=user,
        type=CredentialType.PHARMACY_COUNCIL,
        registration_number="A-1234",
        status=CredentialStatus.PENDING,
    )
    with tenant_context(tenant.tenant.id):
        assign_role(user=user, role=role(system_roles.OWNER))
        assert not resolver.has_permission(user, GATED_CODE)


def test_an_expired_registration_does_not_count(tenant, user, gated_permission):
    """An expired council registration is not a registration."""
    UserCredential.objects.create(
        user=user,
        type=CredentialType.PHARMACY_COUNCIL,
        registration_number="A-1234",
        status=CredentialStatus.VERIFIED,
        expires_on=timezone.localdate() - timedelta(days=1),
    )
    with tenant_context(tenant.tenant.id):
        assign_role(user=user, role=role(system_roles.OWNER))
        assert not resolver.has_permission(user, GATED_CODE)


def test_credential_validity_is_checked_on_the_model_too():
    credential = UserCredential(
        type=CredentialType.PHARMACY_COUNCIL,
        registration_number="A-1",
        status=CredentialStatus.VERIFIED,
    )
    assert credential.is_valid_on()
    credential.expires_on = timezone.localdate() - timedelta(days=1)
    assert not credential.is_valid_on()


def test_permissions_do_not_leak_between_tenants(user):
    """The same person may be an owner in one pharmacy and hold nothing in another."""
    first = make_tenant("alpha", owner=user)
    second = make_tenant("bravo")

    with tenant_context(first.tenant.id):
        assert resolver.has_permission(user, "tenancy.branch.manage")

    with tenant_context(second.tenant.id):
        assert resolver.permissions_for(user) == frozenset()
