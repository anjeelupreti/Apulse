from django.db import migrations

from kernel.foundation.append_only import MakeAppendOnly
from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """Isolation for all three, and append-only for the ledger.

    The ledger is the record of where every unit went, which an inspector may ask to see. A
    mistake is corrected with a reversing entry; history is not edited. Balances stay writable
    because they are a running total derived from the ledger, not a record of anything.
    """

    dependencies = [("inventory", "0001_initial")]

    operations = [
        EnableTenantRowLevelSecurity("Batch"),
        EnableTenantRowLevelSecurity("StockLedgerEntry"),
        EnableTenantRowLevelSecurity("StockBalance"),
        MakeAppendOnly("StockLedgerEntry"),
    ]
