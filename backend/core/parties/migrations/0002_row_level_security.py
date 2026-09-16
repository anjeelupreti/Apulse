from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """Who a pharmacy buys from and sells to is commercially its own."""

    dependencies = [("parties", "0001_initial")]

    operations = [EnableTenantRowLevelSecurity("Party")]
