import pytest

from kernel.tenancy.models import TenantStatus

from .factories import make_tenant

pytestmark = [pytest.mark.django_db, pytest.mark.urls("kernel.tenancy.tests.urls")]


def test_subdomain_resolves_the_tenant_and_opens_its_context(client):
    make_tenant("alpha")
    body = client.get("/whoami/", headers={"host": "alpha.testserver"}).json()
    assert body["tenant_slug"] == "alpha"
    assert body["context_tenant_id"] is not None


def test_unknown_host_continues_without_a_tenant(client):
    """No fallback tenant: an unresolved host gets no context, so tenant data stays invisible."""
    body = client.get("/whoami/", headers={"host": "testserver"}).json()
    assert body["tenant_slug"] is None
    assert body["context_tenant_id"] is None


def test_each_request_gets_its_own_tenant(client):
    make_tenant("alpha")
    make_tenant("bravo")
    first = client.get("/whoami/", headers={"host": "alpha.testserver"}).json()
    second = client.get("/whoami/", headers={"host": "bravo.testserver"}).json()
    assert first["tenant_slug"] == "alpha"
    assert second["tenant_slug"] == "bravo"
    assert first["context_tenant_id"] != second["context_tenant_id"]


def test_suspended_tenant_is_blocked_from_writing(client):
    make_tenant("lapsed", status=TenantStatus.SUSPENDED)
    response = client.post("/whoami/", headers={"host": "lapsed.testserver"})
    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "TENANT_READ_ONLY"
    assert body["message_ne"]


def test_suspended_tenant_can_still_read_its_records(client):
    """Registers and invoices must stay readable: DDA and IRD do not care about unpaid invoices."""
    make_tenant("lapsed", status=TenantStatus.SUSPENDED)
    response = client.get("/whoami/", headers={"host": "lapsed.testserver"})
    assert response.status_code == 200
    assert response.json()["tenant_slug"] == "lapsed"


def test_archived_tenant_is_denied_entirely(client):
    make_tenant("gone", status=TenantStatus.ARCHIVED)
    response = client.get("/whoami/", headers={"host": "gone.testserver"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_INACTIVE"


@pytest.mark.urls("config.urls")  # the real routes, so /healthz exists
def test_health_endpoints_are_exempt_from_tenant_resolution(client):
    response = client.get("/healthz", headers={"host": "nonexistent.testserver"})
    assert response.status_code == 200
