from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """A pharmacy's invoice numbering is its own business and nobody else's."""

    dependencies = [("numbering", "0001_initial")]

    operations = [
        EnableTenantRowLevelSecurity("NumberSeries"),
        EnableTenantRowLevelSecurity("NumberRange"),
    ]
