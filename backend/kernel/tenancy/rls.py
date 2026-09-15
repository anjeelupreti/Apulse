"""PostgreSQL row-level security: the isolation that holds even when application code is wrong."""

from typing import Any

from django.db.migrations.operations.base import Operation

POLICY_NAME = "tenant_isolation"

# NULLIF handles the reset value (''): an unset app.tenant_id yields NULL, the comparison is never
# true, and the query returns nothing. Failing closed is the only safe direction here.
_TENANT_EXPRESSION = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def enable_sql(table: str, column: str = "tenant_id") -> str:
    return f"""
        ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;
        -- FORCE matters: without it the table owner (the role that runs migrations and serves
        -- requests) would bypass every policy below.
        ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}";
        CREATE POLICY {POLICY_NAME} ON "{table}"
            USING ("{column}" = {_TENANT_EXPRESSION})
            WITH CHECK ("{column}" = {_TENANT_EXPRESSION});
    """


def disable_sql(table: str) -> str:
    return f"""
        DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}";
        ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;
    """


class EnableTenantRowLevelSecurity(Operation):
    """Apply the tenant isolation policy to a model's table.

    Every model inheriting `TenantScopedModel` needs one of these in a migration;
    `tests/test_tenant_isolation.py` fails the build if one is missing.
    """

    reversible = True

    def __init__(self, model_name: str, column: str = "tenant_id") -> None:
        self.model_name = model_name
        self.column = column

    def state_forwards(self, app_label: str, state: Any) -> None:
        """No Django-level state changes; this is a database-only concern."""

    # Django calls these positionally; the leading underscore marks the state we do not need.
    def database_forwards(
        self, app_label: str, schema_editor: Any, _from_state: Any, to_state: Any
    ) -> None:
        model = to_state.apps.get_model(app_label, self.model_name)
        schema_editor.execute(enable_sql(model._meta.db_table, self.column))

    def database_backwards(
        self, app_label: str, schema_editor: Any, from_state: Any, _to_state: Any
    ) -> None:
        model = from_state.apps.get_model(app_label, self.model_name)
        schema_editor.execute(disable_sql(model._meta.db_table))

    def describe(self) -> str:
        return f"Enable tenant row-level security on {self.model_name}"

    @property
    def migration_name_fragment(self) -> str:
        return f"rls_{self.model_name.lower()}"
