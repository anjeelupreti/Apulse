from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """Module and Feature describe the product and are shared; what a tenant holds is not.

    FeatureFlag is also platform-wide: a kill switch belongs to us, not to any one account.
    """

    dependencies = [("entitlements", "0001_initial")]

    operations = [
        EnableTenantRowLevelSecurity("TenantModule"),
        EnableTenantRowLevelSecurity("FeatureGrant"),
        EnableTenantRowLevelSecurity("UsageMeter"),
    ]
