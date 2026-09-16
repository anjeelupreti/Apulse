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
