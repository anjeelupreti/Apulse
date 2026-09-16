from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """Units are shared reference data; a pharmacy's own catalogue is not.

    What one pharmacy stocks, what it calls things and what it paid are all commercially its own.
    """

    dependencies = [("catalog", "0001_initial")]

    operations = [
        EnableTenantRowLevelSecurity("ItemCategory"),
        EnableTenantRowLevelSecurity("Manufacturer"),
        EnableTenantRowLevelSecurity("Item"),
        EnableTenantRowLevelSecurity("ItemUnit"),
        EnableTenantRowLevelSecurity("ItemBarcode"),
    ]
