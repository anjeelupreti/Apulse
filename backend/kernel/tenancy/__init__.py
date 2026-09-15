"""Tenancy: tenants, their legal entities, branches, storage locations and memberships.

Isolation is enforced twice, on purpose:

1. Application layer — a tenant-scoped default manager filters every query.
2. Database layer — PostgreSQL row-level security policies.

The second exists because the first is only as good as the code that uses it. One forgotten
`.all_tenants` or a hand-written SQL query would otherwise leak one pharmacy's sales into another's.
"""
