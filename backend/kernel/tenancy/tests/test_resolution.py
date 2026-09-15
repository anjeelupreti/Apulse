import pytest
from django.test import RequestFactory, override_settings

from kernel.tenancy.models import TenantDomain
from kernel.tenancy.resolution import resolve_tenant, slug_from_host

from .factories import make_tenant


@pytest.mark.parametrize(
    ("host", "base", "expected"),
    [
        ("alpha.app.example.com", "app.example.com", "alpha"),
        ("alpha.localhost", "localhost", "alpha"),
        ("app.example.com", "app.example.com", None),  # the bare base domain is not a tenant
        ("alpha.beta.app.example.com", "app.example.com", None),  # no nested subdomains
        ("evil.com", "app.example.com", None),
        ("notapp.example.com", "app.example.com", None),  # suffix match must not be substring match
        ("alpha.localhost", "", None),  # no base domain configured
    ],
)
def test_slug_from_host(host, base, expected):
    with override_settings(TENANT_BASE_DOMAIN=base):
        assert slug_from_host(host) == expected


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=["pharmacy.com.np"])
def test_verified_custom_domain_wins_over_subdomain():
    alpha = make_tenant("alpha")
    TenantDomain.objects.create(
        tenant=alpha.tenant, domain="pharmacy.com.np", is_primary=True, is_verified=True
    )
    request = RequestFactory().get("/", headers={"host": "pharmacy.com.np"})
    assert resolve_tenant(request) == alpha.tenant


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=["unverified.com.np"])
def test_unverified_custom_domain_does_not_resolve():
    """Otherwise anyone could claim another business's domain by typing it in."""
    alpha = make_tenant("alpha")
    TenantDomain.objects.create(tenant=alpha.tenant, domain="unverified.com.np", is_verified=False)
    request = RequestFactory().get("/", headers={"host": "unverified.com.np"})
    assert resolve_tenant(request) is None


@pytest.mark.django_db
@override_settings(TENANT_BASE_DOMAIN="testserver", TENANT_ALLOW_HEADER_RESOLUTION=False)
def test_tenant_header_is_ignored_by_default():
    """A header alone is not proof of anything until the token carries a verified tenant claim."""
    make_tenant("alpha")
    request = RequestFactory().get("/", headers={"host": "testserver", "x-tenant": "alpha"})
    assert resolve_tenant(request) is None


@pytest.mark.django_db
@override_settings(TENANT_BASE_DOMAIN="testserver", TENANT_ALLOW_HEADER_RESOLUTION=True)
def test_tenant_header_resolves_when_explicitly_enabled():
    alpha = make_tenant("alpha")
    request = RequestFactory().get("/", headers={"host": "testserver", "x-tenant": "alpha"})
    assert resolve_tenant(request) == alpha.tenant
