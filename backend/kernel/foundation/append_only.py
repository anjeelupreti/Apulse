"""Making a table append-only in the database rather than by convention.

Used for records that are evidence: the audit trail, and the stock ledger. Both are things an
inspector may ask to see, and both are worthless if the application can quietly rewrite them.
Corrections are made by posting a reversing entry, never by editing history.
"""

from typing import Any

from django.db.migrations.operations.base import Operation


def enable_sql(table: str, function: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '{table} is append-only; % is not permitted', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER {function}_no_update
            BEFORE UPDATE ON "{table}"
            FOR EACH ROW EXECUTE FUNCTION {function}();

        CREATE TRIGGER {function}_no_delete
            BEFORE DELETE ON "{table}"
            FOR EACH ROW EXECUTE FUNCTION {function}();

        -- Row triggers do not fire for TRUNCATE, so without this the table could be emptied
        -- in a single statement.
        CREATE TRIGGER {function}_no_truncate
            BEFORE TRUNCATE ON "{table}"
            FOR EACH STATEMENT EXECUTE FUNCTION {function}();
    """


def disable_sql(table: str, function: str) -> str:
    return f"""
        DROP TRIGGER IF EXISTS {function}_no_update ON "{table}";
        DROP TRIGGER IF EXISTS {function}_no_delete ON "{table}";
        DROP TRIGGER IF EXISTS {function}_no_truncate ON "{table}";
        DROP FUNCTION IF EXISTS {function}();
    """


class MakeAppendOnly(Operation):
    """Refuse UPDATE, DELETE and TRUNCATE on a model's table."""

    reversible = True

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def state_forwards(self, app_label: str, state: Any) -> None:
        """Database-only; nothing changes in Django's model state."""

    def _function_name(self, table: str) -> str:
        return f"{table}_append_only"

    def database_forwards(
        self, app_label: str, schema_editor: Any, _from_state: Any, to_state: Any
    ) -> None:
        table = to_state.apps.get_model(app_label, self.model_name)._meta.db_table
        # params=None: the SQL contains a literal % in the RAISE message, which would otherwise
        # be read as a query placeholder.
        schema_editor.execute(enable_sql(table, self._function_name(table)), params=None)

    def database_backwards(
        self, app_label: str, schema_editor: Any, from_state: Any, _to_state: Any
    ) -> None:
        table = from_state.apps.get_model(app_label, self.model_name)._meta.db_table
        schema_editor.execute(disable_sql(table, self._function_name(table)), params=None)

    def describe(self) -> str:
        return f"Make {self.model_name} append-only"

    @property
    def migration_name_fragment(self) -> str:
        return f"append_only_{self.model_name.lower()}"
