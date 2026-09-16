from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """A credit note is one pharmacy's tax document, isolated like the invoice it credits."""

    dependencies = [("sales", "0003_creditnote_creditnoteline_and_more")]

    operations = [
        EnableTenantRowLevelSecurity("CreditNote"),
        EnableTenantRowLevelSecurity("CreditNoteLine"),
    ]
