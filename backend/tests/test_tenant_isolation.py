"""The isolation suite: proof that one pharmacy cannot reach another pharmacy's data.

These tests are the reason the application connects to PostgreSQL as a role that cannot bypass
row-level security. They must never be weakened to make an unrelated test pass.
"""

import pytest
from django.apps import apps
from django.db import DatabaseError, connection, transaction

from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Branch, LegalEntity, Location, TenantScopedModel
from kernel.tenancy.rls import POLICY_NAME
from kernel.tenancy.tests.factories import make_tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_tenants():
    alpha = make_tenant("alpha")
    bravo = make_tenant("bravo")
    return alpha, bravo


# --------------------------------------------------------------------------- the environment
def test_database_role_cannot_bypass_row_level_security():
    """If this fails, every other isolation test below is meaningless.

    A superuser (or a role with BYPASSRLS) ignores every policy, so the tests would pass while
    production leaked. Postgres also ignores policies for a table's owner unless the table is set
    to FORCE row level security.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        is_superuser, can_bypass = cursor.fetchone()
    assert not is_superuser, "The application role must not be a PostgreSQL superuser."
    assert not can_bypass, "The application role must not have BYPASSRLS."


def test_every_tenant_scoped_model_is_protected():
    """Guard against the most likely future mistake: a new tenant table with no policy."""
    scoped_models = [
        model
        for model in apps.get_models()
        if issubclass(model, TenantScopedModel) and not model._meta.abstract
    ]
    assert scoped_models, "Expected at least one tenant-scoped model."
    expected_tables = {model._meta.db_table for model in scoped_models}

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_policies p ON p.tablename = c.relname AND p.policyname = %s
            WHERE c.relname = ANY(%s) AND c.relrowsecurity AND c.relforcerowsecurity
            """,
            [POLICY_NAME, list(expected_tables)],
        )
        protected = {row[0] for row in cursor.fetchall()}

    missing = expected_tables - protected
    assert not missing, (
        f"Tenant-scoped tables without an enforced isolation policy: {sorted(missing)}. "
        f"Add kernel.tenancy.rls.EnableTenantRowLevelSecurity for each in a migration."
    )


# --------------------------------------------------------------------------- reads
def test_queries_see_only_the_active_tenant(two_tenants):
    alpha, _bravo = two_tenants
    with tenant_context(alpha.tenant.id):
        assert Branch.objects.count() == 1
        assert Branch.objects.get() == alpha.branch


def test_the_unscoped_manager_is_still_blocked_by_the_database(two_tenants):
    """`all_tenants` removes the application filter. The database keeps the guarantee."""
    alpha, _bravo = two_tenants
    with tenant_context(alpha.tenant.id):
        assert Branch.all_tenants.count() == 1
        assert LegalEntity.all_tenants.count() == 1
        assert Location.all_tenants.count() == 4


def test_raw_sql_cannot_reach_another_tenant(two_tenants):
    """Hand-written SQL bypasses every manager, so this is the case RLS exists for."""
    alpha, _bravo = two_tenants
    with tenant_context(alpha.tenant.id), connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM tenancy_branch")
        assert cursor.fetchone()[0] == 1


def test_fetching_another_tenants_row_by_primary_key_finds_nothing(two_tenants):
    alpha, bravo = two_tenants
    with tenant_context(alpha.tenant.id):
        assert not Branch.all_tenants.filter(pk=bravo.branch.pk).exists()


def test_nothing_is_visible_without_a_tenant_context(two_tenants):
    """Fail closed: no context must mean no data, never all data."""
    assert Branch.all_tenants.count() == 0
    assert Branch.objects.count() == 0


# --------------------------------------------------------------------------- writes
def test_inserting_a_row_for_another_tenant_is_rejected(two_tenants):
    alpha, bravo = two_tenants
    with (
        tenant_context(alpha.tenant.id),
        pytest.raises(DatabaseError, match="row-level security"),
        transaction.atomic(),
    ):
        Branch.all_tenants.create(
            tenant_id=bravo.tenant.id,
            legal_entity_id=bravo.legal_entity.id,
            code="SMUGGLED",
            name="Smuggled branch",
        )


def test_updating_another_tenants_row_changes_nothing(two_tenants):
    alpha, bravo = two_tenants
    with tenant_context(alpha.tenant.id):
        assert Branch.all_tenants.filter(pk=bravo.branch.pk).update(name="Renamed") == 0

    with tenant_context(bravo.tenant.id):
        bravo.branch.refresh_from_db()
        assert bravo.branch.name != "Renamed"


def test_deleting_another_tenants_row_deletes_nothing(two_tenants):
    alpha, bravo = two_tenants
    with tenant_context(alpha.tenant.id):
        deleted, _ = Location.all_tenants.filter(branch_id=bravo.branch.pk).delete()
        assert deleted == 0

    with tenant_context(bravo.tenant.id):
        assert Location.objects.filter(branch=bravo.branch).count() == 4


def test_tenant_is_filled_in_from_the_context(two_tenants):
    alpha, _bravo = two_tenants
    with tenant_context(alpha.tenant.id):
        location = Location.objects.create(
            branch=alpha.branch, code="RACK-A1", name="Rack A1", type="rack"
        )
        assert location.tenant_id == alpha.tenant.id


def test_writing_without_a_context_raises_instead_of_guessing(two_tenants):
    alpha, _bravo = two_tenants
    from kernel.tenancy.context import NoActiveTenantError

    with pytest.raises(NoActiveTenantError):
        Location(branch_id=alpha.branch.id, code="X", name="X", type="rack").save()
