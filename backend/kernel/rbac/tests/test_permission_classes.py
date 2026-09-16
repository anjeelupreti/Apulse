import pytest
from rest_framework.test import APIClient

from kernel.identity.models import User
from kernel.rbac import system_roles
from kernel.rbac.models import Role
from kernel.rbac.services import assign_role
from kernel.tenancy.context import tenant_context
from kernel.tenancy.tests.factories import make_tenant

pytestmark = [pytest.mark.django_db, pytest.mark.urls("kernel.rbac.tests.urls")]

HOST = {"host": "alpha.testserver"}


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user():
    return User.objects.create_user("ram@example.com", "password-1234", full_name="Ram")


def test_signed_out_callers_are_refused(client):
    make_tenant("alpha")
    response = client.get("/manage-branches/", headers=HOST)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_NOT_AUTHENTICATED"


def test_a_signed_in_user_without_the_permission_is_refused(client, user):
    make_tenant("alpha", owner=None)
    client.force_authenticate(user)
    response = client.get("/manage-branches/", headers=HOST)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_a_user_with_the_permission_is_allowed(client, user):
    make_tenant("alpha", owner=user)
    client.force_authenticate(user)
    assert client.get("/manage-branches/", headers=HOST).status_code == 200


def test_the_inline_factory_form_works(client, user):
    provisioned = make_tenant("alpha")
    client.force_authenticate(user)
    assert client.get("/inline/", headers=HOST).status_code == 403

    with tenant_context(provisioned.tenant.id):
        assign_role(user=user, role=Role.objects.get(code=system_roles.ADMINISTRATOR))
    # Administrator may view roles but not edit them.
    assert client.get("/inline/", headers=HOST).status_code == 403

    with tenant_context(provisioned.tenant.id):
        assign_role(user=user, role=Role.objects.get(code=system_roles.OWNER))
    assert client.get("/inline/", headers=HOST).status_code == 200


def test_requests_without_a_resolved_tenant_are_refused(client, user):
    """Otherwise a misrouted request would look like an empty pharmacy."""
    make_tenant("alpha")
    client.force_authenticate(user)
    response = client.get("/tenant-only/", headers={"host": "testserver"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TENANT_NOT_FOUND"


def test_permissions_are_evaluated_per_tenant(client, user):
    """Owner of one pharmacy, nobody in another."""
    make_tenant("alpha", owner=user)
    make_tenant("bravo")
    client.force_authenticate(user)

    assert client.get("/manage-branches/", headers=HOST).status_code == 200
    assert client.get("/manage-branches/", headers={"host": "bravo.testserver"}).status_code == 403
