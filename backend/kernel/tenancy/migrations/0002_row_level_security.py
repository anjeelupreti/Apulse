from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """Enable tenant row-level security on every tenant-scoped table.

    Registry tables (Tenant, TenantDomain, TenantMembership) are deliberately excluded: they are
    read while resolving which tenant a request belongs to, and while listing the tenants a person
    may sign in to — both of which happen before any tenant context exists.

    Any future model inheriting TenantScopedModel needs an operation like these;
    `tests/test_tenant_isolation.py` fails the build if one is missing.
    """

    dependencies = [("tenancy", "0001_initial")]

    operations = [
        EnableTenantRowLevelSecurity("LegalEntity"),
        EnableTenantRowLevelSecurity("Branch"),
        EnableTenantRowLevelSecurity("Location"),
    ]
