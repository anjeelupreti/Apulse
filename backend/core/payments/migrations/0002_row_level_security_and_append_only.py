from django.db import migrations

from kernel.foundation.append_only import MakeAppendOnly
from kernel.tenancy.rls import EnableTenantRowLevelSecurity


class Migration(migrations.Migration):
    """Isolation for all five, and append-only for the two that record money moving.

    A payment and a cash movement are evidence. A till that can be quietly re-added-up after the
    count proves nothing, so a mistake is corrected by recording its opposite, exactly as the
    stock ledger works.

    The shift itself stays writable: it opens, takes a count and gets signed off, and those are
    changes to a record rather than rewritings of history. The denomination sheet is rewritable
    because a recount before the close is a recount, not a cover-up — what it finally says is
    fixed when the shift closes, and the closing figures are on the shift.
    """

    dependencies = [("payments", "0001_initial")]

    operations = [
        EnableTenantRowLevelSecurity("PaymentMode"),
        EnableTenantRowLevelSecurity("Payment"),
        EnableTenantRowLevelSecurity("CashierShift"),
        EnableTenantRowLevelSecurity("CashMovement"),
        EnableTenantRowLevelSecurity("DenominationCount"),
        MakeAppendOnly("Payment"),
        MakeAppendOnly("CashMovement"),
    ]
