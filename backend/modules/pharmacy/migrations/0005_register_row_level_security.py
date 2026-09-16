from django.db import migrations

from kernel.foundation.append_only import MakeAppendOnly
from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """Isolation for both, and append-only for the register itself.

    The register is evidence. An inspector asking what happened to a box of morphine has to get
    the whole story, including the parts somebody would rather not show, so the database refuses
    to update or delete a line. A mistake is corrected by a correction entry that points at what
    it corrects.

    The running balance stays writable: it is a total derived from the entries, not a record of
    anything, and `reconcile_register()` reports when the two disagree.
    """

    dependencies = [("pharmacy", "0004_narcoticregisterbalance_narcoticregisterentry")]

    operations = [
        EnableTenantRowLevelSecurity("NarcoticRegisterEntry"),
        EnableTenantRowLevelSecurity("NarcoticRegisterBalance"),
        MakeAppendOnly("NarcoticRegisterEntry"),
    ]
