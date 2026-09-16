from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """Purchase prices are among the most commercially sensitive data a pharmacy holds."""

    dependencies = [("purchasing", "0001_initial")]

    operations = [
        EnableTenantRowLevelSecurity("GoodsReceipt"),
        EnableTenantRowLevelSecurity("GoodsReceiptLine"),
    ]
