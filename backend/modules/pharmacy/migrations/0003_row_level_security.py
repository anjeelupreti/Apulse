from django.db import migrations

from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """Prescriptions are patient data, and the most sensitive thing a pharmacy holds.

    ScheduleRule is deliberately excluded: those rules come from DDA and are the same for every
    pharmacy in the country.
    """

    dependencies = [("pharmacy", "0002_initial")]

    operations = [
        EnableTenantRowLevelSecurity("MedicineProfile"),
        EnableTenantRowLevelSecurity("Prescription"),
    ]
