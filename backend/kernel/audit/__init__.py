"""The audit trail: who did what, when, from where, and to which record.

Two properties make it worth trusting rather than merely having:

* **Append-only**, enforced by a database trigger, not by application discipline.
* **Hash-chained** per tenant, so removing or altering an entry breaks the chain and
  `verify_chain()` reports exactly where.

This is what turns "our system keeps records" into something a DDA inspector or an IRD auditor can
be shown.
"""
