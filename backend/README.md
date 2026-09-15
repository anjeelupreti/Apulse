# Backend: Django API & Workers

Python 3.12 · Django 5 · DRF · drf-spectacular · Celery · Channels · PostgreSQL 16 (RLS) · Redis · uv

## Planned layout

```
backend/
├── pyproject.toml            # uv-managed deps, ruff, mypy, pytest, import-linter config
├── uv.lock
├── manage.py
├── .env.example
├── config/
│   ├── settings/{base,local,test,staging,production}.py
│   ├── urls.py               # /api/v1/, /console-api/v1/, /healthz, /readyz, /version
│   ├── asgi.py  wsgi.py
│   └── celery.py             # queues: default, critical, bulk, notifications, integrations
│
├── shared/                   # framework-agnostic utilities (no Django models)
│   ├── money/                # Money, rounding, amount-in-words (en/ne, lakh/crore)
│   ├── quantity/             # base-unit quantities, pack conversions
│   ├── nepali_calendar/      # BS↔AD, fiscal year, Nepali numerals
│   ├── ids/                  # UUIDv7
│   ├── errors/               # DomainError + error code catalogue
│   └── typing/
│
├── kernel/                   # always on, never sold
│   ├── tenancy/              # Tenant, LegalEntity, Branch, Location, Device, RLS helpers, middleware
│   ├── identity/             # User, Membership, auth, 2FA, sessions, devices, PIN switch
│   ├── rbac/                 # Permission registry, Role, RoleAssignment, credentials gating
│   ├── audit/                # AuditEvent (hash-chained), history API
│   ├── modules/              # ModuleManifest, registry sync, lifecycle hooks
│   ├── entitlements/         # resolver, overrides, usage meters, feature flags, read-only mode
│   ├── settings_engine/      # scoped typed settings
│   ├── numbering/            # series, FY rollover, device range leasing
│   ├── files/                # FileObject, presigned upload, scanning
│   ├── notifications/        # channels, templates, preferences, in-app centre
│   ├── events/               # outbox, dispatcher, schema registry, webhooks
│   ├── jobs/                 # job centre (imports/exports/reports status)
│   ├── dataio/               # ImportSpec/ExportSpec framework
│   ├── printing/             # templates → PDF / ESC-POS, barcodes, labels
│   ├── sync/                 # offline sync protocol endpoints
│   └── geo/                  # Nepal provinces/districts/local levels/wards
│
├── core/                     # shared domain reused by all verticals
│   ├── parties/  patients/  practitioners/
│   ├── catalog/  pricing/  inventory/
│   ├── purchasing/  sales/  tax/  payments/  accounting/
│   └── reporting/            # report framework
│
├── modules/                  # sellable verticals (each has module.py manifest)
│   ├── pharmacy/
│   ├── pharmacy_compliance/
│   ├── ird_ebilling/
│   ├── engagement/
│   ├── chain/
│   ├── wholesale/
│   ├── b2b_connect/
│   ├── hospital_pharmacy/
│   ├── intelligence/
│   ├── omnichannel/
│   └── (future) warehouse/ clinic/ dental/ lab/ hospital/
│
├── control/                  # platform owner console backend (/console-api/v1/)
│   ├── staff/  tenants_admin/  catalogue_pricing/  subscriptions/
│   ├── platform_billing/  platform_accounting/
│   ├── crm/  tasks/  helpdesk/  knowledge_base/
│   ├── governance/           # policies, rule sets, announcements, maintenance, recall broadcast
│   ├── releases/  flags_console/  system_health/
│   └── analytics/
│
├── integrations/             # adapters behind ports
│   ├── ird_cbms/  esewa/  khalti/  fonepay/  connectips/
│   ├── sms/  whatsapp/  email/
│   ├── hl7_fhir/  distributor_edi/  temperature_loggers/  insurance_ssf/
│   └── base/                 # retry, logging, sandbox, health contract
│
└── tests/                    # cross-cutting suites (tenant isolation harness, architecture tests)
```

## Layer rules (enforced by import-linter)
`shared` ← `kernel` ← `core` ← `modules`; `control` → kernel only; `integrations` are reached through ports. See [docs/ARCHITECTURE.md §3](../docs/ARCHITECTURE.md). Five contracts run in CI; a violating import fails the build rather than being caught in review.

## Commands
Run everything through the root task runner (`python tasks.py`), from the repository root:

```bash
python tasks.py setup      # uv sync, create backend/.env, install git hooks
python tasks.py infra-up   # PostgreSQL 55432, Redis 56379, MinIO 59000, Mailpit 51025/51026
python tasks.py migrate
python tasks.py dev        # http://127.0.0.1:8000
python tasks.py lint       # ruff + format + import-linter + mypy + missing-migration check
python tasks.py test
python tasks.py openapi    # backend/openapi/schema.yaml
```

Useful URLs: `/healthz`, `/readyz`, `/version`, `/api/v1/me/`, `/api/docs/`, `/django-admin/`.

## What exists today (M1.2 complete)
- Environment-driven split settings; required variables have no default, so a misconfigured
  deployment fails at startup rather than silently running on a dev value.
- `identity.User` with UUIDv7 primary key and email **or** phone login, enforced by a DB constraint.
  Set before the first migration, because changing `AUTH_USER_MODEL` later is a painful migration.
- Standard bilingual (en/ne) error envelope over a registered error-code catalogue.
- Request-id correlation on every request and propagated into Celery tasks.
- `/healthz` deliberately never touches the database: a liveness probe that needs the DB turns a
  brief DB blip into a container restart loop.
- Tests run against real PostgreSQL as a **non-superuser role without `BYPASSRLS`**, so the
  row-level security added in M2.1 is exercised exactly as in production.

## Next
Phase 2 (kernel): tenancy + RLS, authentication/2FA, RBAC, audit, module registry, entitlements.
See [docs/CHECKLIST.md](../docs/CHECKLIST.md).
