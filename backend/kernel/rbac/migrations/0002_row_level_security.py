from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """Roles and who holds them are tenant data, so they carry the same isolation policy."""

    dependencies = [("rbac", "0001_initial")]

    operations = [
        EnableTenantRowLevelSecurity("Role"),
        EnableTenantRowLevelSecurity("RolePermission"),
        EnableTenantRowLevelSecurity("RoleAssignment"),
    ]
