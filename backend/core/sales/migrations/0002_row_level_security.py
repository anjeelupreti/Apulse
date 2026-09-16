from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """Sales records are a pharmacy's most sensitive data, and include who bought what."""

    dependencies = [("sales", "0001_initial")]

    operations = [
        EnableTenantRowLevelSecurity("SalesInvoice"),
        EnableTenantRowLevelSecurity("SalesInvoiceLine"),
        EnableTenantRowLevelSecurity("SalesInvoiceLineBatch"),
    ]
