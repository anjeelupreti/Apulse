from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    dependencies = [("practitioners", "0001_initial")]

    operations = [EnableTenantRowLevelSecurity("Practitioner")]
