import pytest
from django.db import connection

from kernel.tenancy.context import (
    NoActiveTenantError,
    get_current_tenant_id,
    require_current_tenant_id,
    tenant_context,
)

from .factories import make_tenant_only

pytestmark = pytest.mark.django_db


def db_tenant_setting() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.tenant_id', true)")
        return (cursor.fetchone()[0]) or ""


def test_context_sets_both_python_and_database_state():
    tenant = make_tenant_only("alpha")
    assert get_current_tenant_id() is None

    with tenant_context(tenant.id):
        assert get_current_tenant_id() == tenant.id
        assert db_tenant_setting() == str(tenant.id)

    assert get_current_tenant_id() is None
    assert db_tenant_setting() == ""


def test_nested_contexts_restore_the_outer_tenant():
    outer = make_tenant_only("outer")
    inner = make_tenant_only("inner")

    with tenant_context(outer.id):
        with tenant_context(inner.id):
            assert get_current_tenant_id() == inner.id
            assert db_tenant_setting() == str(inner.id)
        # The inner block must not leave the outer block talking to the wrong tenant.
        assert get_current_tenant_id() == outer.id
        assert db_tenant_setting() == str(outer.id)


def test_context_accepts_a_string_id():
    tenant = make_tenant_only("alpha")
    with tenant_context(str(tenant.id)) as active:
        assert active == tenant.id


def test_context_is_cleared_even_when_the_block_raises():
    tenant = make_tenant_only("alpha")
    with pytest.raises(ValueError, match="boom"), tenant_context(tenant.id):
        raise ValueError("boom")
    assert get_current_tenant_id() is None


def test_require_current_tenant_id_fails_loudly_outside_a_context():
    with pytest.raises(NoActiveTenantError, match="No active tenant"):
        require_current_tenant_id()
