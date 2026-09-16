from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """One account's settings are one account's business.

    More than a privacy matter here: a setting decides whether a prescription is demanded and how
    a total is rounded, so a row readable across accounts would be a row that could change another
    pharmacy's rules.
    """

    dependencies = [("settings", "0001_initial")]

    operations = [EnableTenantRowLevelSecurity("SettingValue")]
