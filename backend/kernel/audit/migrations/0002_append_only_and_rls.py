from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity

# Append-only enforced by the database rather than by application discipline. An audit trail that
# the application can quietly rewrite is not evidence of anything.
#
# TRUNCATE gets its own statement-level trigger: row triggers do not fire for it, so without this
# the whole table could be emptied in one statement.
APPEND_ONLY = """
CREATE OR REPLACE FUNCTION audit_event_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditevent is append-only; % is not permitted', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_event_no_update
    BEFORE UPDATE ON audit_auditevent
    FOR EACH ROW EXECUTE FUNCTION audit_event_append_only();

CREATE TRIGGER audit_event_no_delete
    BEFORE DELETE ON audit_auditevent
    FOR EACH ROW EXECUTE FUNCTION audit_event_append_only();

CREATE TRIGGER audit_event_no_truncate
    BEFORE TRUNCATE ON audit_auditevent
    FOR EACH STATEMENT EXECUTE FUNCTION audit_event_append_only();
"""

DROP_APPEND_ONLY = """
DROP TRIGGER IF EXISTS audit_event_no_update ON audit_auditevent;
DROP TRIGGER IF EXISTS audit_event_no_delete ON audit_auditevent;
DROP TRIGGER IF EXISTS audit_event_no_truncate ON audit_auditevent;
DROP FUNCTION IF EXISTS audit_event_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [
        EnableTenantRowLevelSecurity("AuditEvent"),
        EnableTenantRowLevelSecurity("AuditChainHead"),
        migrations.RunSQL(sql=APPEND_ONLY, reverse_sql=DROP_APPEND_ONLY),
    ]
