# Changelog

All notable changes are recorded here. Format: [Keep a Changelog](https://keepachangelog.com);
versioning: [Semantic Versioning](https://semver.org).

## [Unreleased]

### Added
- Planning documents: architecture, master build checklist, engineering conventions, control-plane
  design, compliance register, ADR template.
- Repository root: task runner (`tasks.py`), pre-commit hooks, contributor and security policies,
  issue/PR templates, backend CI workflow.
- Backend skeleton: environment-driven split settings, UUIDv7 base models, custom `identity.User`
  (email *or* phone login), DRF with deny-by-default permissions, bilingual error envelope with a
  registered error-code catalogue, request-id logging, health/readiness/version endpoints, Celery
  queues with request-id propagation, Channels, OpenAPI schema, enforced layering.
- Local development stack: PostgreSQL (non-superuser app role so row-level security is exercised),
  Redis, MinIO, Mailpit.
- Multi-tenancy (kernel): tenant registry, legal entities, branches with DDA licence fields, and
  stock locations; tenant context bound to both the application and the database session;
  PostgreSQL row-level security on every tenant-scoped table, enforced even for the table owner;
  tenant resolution by verified custom domain or subdomain; read-only enforcement for suspended
  accounts that still allows reading, printing and exporting regulatory records; idempotent tenant
  provisioning that creates a locked narcotics cabinet and a quarantine location for every branch.
- Nepal administrative divisions with an idempotent `import_geo` command; the seven provinces ship
  with the code.
- UI design direction recorded ahead of the frontend work (`docs/DESIGN_DIRECTION.md`).
- Authentication: sign in with an email address or a phone number; session cookies with a CSRF
  bootstrap endpoint; two-factor authentication with an authenticator app plus single-use recovery
  codes; lockout after repeated failures; a security log of every sign-in attempt; and
  `/api/v1/me/context` returning the user, tenant, memberships and branches in one call.
  Signing in on a tenant's own address requires an active membership of that tenant.
- Access control: a registry of every permission the code checks; twelve built-in roles seeded into
  each account, from Owner to DDA Inspector; roles scoped to the whole account, one business or one
  branch; assignments that can expire, for inspection visits and locum cover; and professional
  registrations (`UserCredential`), so actions that require a registered pharmacist stay closed to
  everyone else whatever their role. `/api/v1/me/context` now returns the caller's permissions.
- Audit trail: every recorded action is hash-chained to the one before it, per account, and the
  database refuses to update, delete or truncate the table. `verify_chain()` reports whether the
  trail is intact and, if not, exactly where it breaks. Changes are recorded field by field, with
  secrets shown as changed but never printed. Permission changes are recorded automatically.
- Modules and entitlements: modules are declared in code and synced into the database so plans can
  reference them; what an account may use resolves from its installed modules and granted features.
  Plans set the base, add-ons add to it, and a manual override replaces the result. Feature flags
  give a kill switch and staged rollouts. Account limits, such as how many branches a plan
  includes, are enforced in the service layer, so the ceiling holds however a branch is created.
  `/api/v1/me/context` now returns the account's features and limits alongside its permissions.
- Bikram Sambat: conversion between BS and Gregorian dates, Nepal's Shrawan-to-Ashadh fiscal year,
  and validators that check a calendar table before it is trusted. No calendar table ships with the
  code: the month lengths are published rather than calculated, and one wrong day would shift the
  date on every later invoice. Supply a verified table and check it with `validate_bs_calendar`.
- Nepali number formatting: 1,00,000 rather than 100,000, Devanagari numerals, rupee amounts, and
  totals written in words using lakh and crore, as a tax invoice requires.
- Document numbering: each branch gets its own run of invoice numbers per fiscal year, restarting
  at 1 on Shrawan 1, with the number format and the counter frozen once the first number has been
  issued. Offline counters are lent a block of numbers in advance so they can keep billing without
  a connection, and the server skips past anything it has lent.
- Tax categories with dated rates, so an old invoice is always re-priced at the rate it carried.
  Which category a medicine belongs to is deliberately not assumed: every item must be classified.
- The item catalogue. Stock is counted in base units — a tablet, a millilitre — and packs are
  conversions on top, so selling four tablets out of a strip and receiving twenty boxes of ten
  strips are the same arithmetic. Barcodes identify the pack, so scanning a box adds a box.
  Quantities read the way a storekeeper counts: "2 boxes 4 strips 7 tablets", not "247 tablets".
- Batches and the stock ledger. Every receipt, sale, adjustment and write-off is recorded, and the
  database refuses to change or delete those records; a mistake is corrected by a reversing entry.
  Stock is issued nearest-expiry-first, and expired or quarantined stock is never picked. Selling
  expired stock is refused outright, while writing it off or returning it stays possible.
- Suppliers and customers as a single record, since in a pharmacy they overlap.
- Goods receipts. A delivery is entered as a draft and moves no stock until it is posted; posting
  creates the batches, brings the stock in and numbers the document, all at once. Bonus quantity
  ("10 + 1 free") is treated as stock that lowers the cost of the whole line, delivery charges are
  spread across lines, and VAT is counted as cost only for a pharmacy that cannot reclaim it.
  Entering the same supplier invoice twice is refused, as is receiving stock that has already
  expired unless someone confirms it deliberately.
