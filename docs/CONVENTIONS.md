# Engineering Conventions

> Applies to every contributor and every module. Changes to this file require an ADR or tech-lead approval.

---

## 1. Repository & Git

| Topic | Rule |
|-------|------|
| Branching | Trunk-based. `main` is always releasable. Short-lived branches: `feat/<scope>-<desc>`, `fix/…`, `chore/…`, `docs/…`, `refactor/…` |
| Commits | [Conventional Commits](https://www.conventionalcommits.org): `feat(pharmacy): add FEFO override reason` |
| Scopes | `kernel`, `control`, `core-<app>`, `<module>`, `web`, `console`, `ui`, `deploy`, `docs`, `ci` |
| PR size | Aim < 400 changed lines (excluding generated files). Split migrations from behaviour when risky |
| Reviews | 1 approval; **2** for kernel, tenancy, auth, tax, numbering, narcotic register, sync, billing |
| Merge | Squash merge; PR title becomes commit message |
| Versioning | SemVer for the platform (`MAJOR.MINOR.PATCH`); module manifests have their own versions |
| Generated code | Committed (`frontend/packages/api-client/src/gen/`), never hand-edited, CI verifies freshness |

## 2. Naming

| Thing | Convention | Example |
|-------|-----------|---------|
| Django app | `snake_case`, singular domain noun | `inventory`, `pharmacy_compliance` |
| Model | `PascalCase` singular | `StockLedgerEntry` |
| DB table | `<app>_<model>` (Django default) | `inventory_stockledgerentry` |
| Permission code | `<module>.<resource>.<action>` | `pharmacy.narcotic_register.view` |
| Feature code | `<module>.<feature>` | `pharmacy.offline_pos` |
| Event name | `<module>.<entity>.<past_tense_verb>` | `core.sales.invoice_posted` |
| Celery task | `<app>.tasks.<verb_noun>` | `ird_ebilling.tasks.push_invoice` |
| API path | plural kebab-case nouns | `/api/v1/stock-adjustments/` |
| JSON fields | `snake_case` | `expiry_date`, `unit_price` |
| TS files | `kebab-case.tsx`; components `PascalCase` exports | `stock-table.tsx` → `StockTable` |
| React hooks | `useXxx` | `useEntitlements` |
| i18n keys | `<module>.<screen>.<element>` | `pharmacy.pos.payment.change_due` |
| Env vars | `UPPER_SNAKE`, prefixed by service | `BACKEND_DATABASE_URL`, `WEB_PUBLIC_API_URL` |
| Document numbers | `{TYPE}-{BRANCH}-{FY}-{SEQ}` (configurable) | `INV-KTM01-8283-000123` |

## 3. Backend (Django)

### 3.1 Code organisation inside an app
```
<app>/
  module.py          # manifest (sellable modules only)
  models/            # one file per aggregate when > 300 lines
  services/          # business logic (write side) — the ONLY place that mutates domain state
  selectors/         # read-side query functions
  api/
    serializers.py
    views.py         # thin: validate → call service/selector → serialize
    urls.py
    filters.py
  events.py          # published event dataclasses + handlers registration
  tasks.py           # Celery tasks (thin wrappers over services)
  rules/             # rule sets (tax, drug) where relevant
  imports.py         # ImportSpec definitions
  exports.py         # ExportSpec definitions
  reports/           # report definitions
  templates/         # print templates
  permissions.py
  settings_schema.py
  admin.py           # internal/debug only; not the product UI
  migrations/
  tests/
    factories.py
    test_services_*.py
    test_api_*.py
    test_isolation.py
```

### 3.2 Rules
- **Views never contain business logic.** Services are plain functions with keyword-only args, typed, transactional (`@transaction.atomic`), and emit events via outbox.
- **No `Model.objects.all()` on tenant models outside selectors.** Use the tenant-scoped manager.
- **No signals for business logic** (only for audit capture & cache invalidation). Use explicit events.
- **Money** → `shared.money.Money` / `Decimal`; **never float**. Quantity → `Decimal` base unit.
- **Time** → `django.utils.timezone.now()`; store UTC; business dates as `DateField` (AD) with BS derived.
- **Every write endpoint** accepts `Idempotency-Key`; every mutable resource exposes `version` for optimistic locking.
- **Migrations** must be backward compatible with the previous release (expand → migrate → contract). No `RunPython` that loads full tables into memory; batch it.
- Raise domain exceptions (`shared.errors.DomainError` subclasses with `code`), never bare `ValidationError` from services.
- Type hints required; `mypy --strict` for `kernel`, `core`, `shared`.

## 4. API

### 4.1 URLs & methods
```
GET    /api/v1/items/                list (page or cursor)
POST   /api/v1/items/                create
GET    /api/v1/items/{id}/           retrieve
PATCH  /api/v1/items/{id}/           partial update (requires version)
POST   /api/v1/items/{id}/archive/   state change as action
POST   /api/v1/items/{id}/restore/
POST   /api/v1/items/bulk/           bulk operations {action, ids, payload}
POST   /api/v1/items/imports/        start import job
POST   /api/v1/items/exports/        start export job
GET    /api/v1/jobs/{id}/            job status
POST   /api/v1/sales-invoices/{id}/post/
POST   /api/v1/sales-invoices/{id}/cancel/   (creates credit note where applicable)
```
- `PUT` is not used. `DELETE` only for drafts and truly deletable resources.
- Tenant is **never** in the URL for tenant APIs (resolved from host/token). Control-plane APIs live under `/console-api/v1/`.

### 4.2 Query parameters
| Param | Meaning |
|-------|---------|
| `page`, `page_size` | Offset pagination (UI lists) — max `page_size` 500 |
| `cursor`, `limit` | Cursor pagination (sync, large exports) |
| `ordering` | `-created_at,name` |
| `search` | Full-text/trigram search |
| `fields` / `expand` | Sparse fieldsets / embed related |
| `updated_since` | ISO timestamp for delta sync |
| `branch` | Filter by branch id(s) — always permission-checked |
| `date_from`, `date_to` | AD ISO dates; `date_system=bs` accepted for convenience |

### 4.3 Response envelopes
List:
```json
{ "count": 1234, "next": "...", "previous": null, "results": [ ... ] }
```
Error (always this shape):
```json
{
  "error": {
    "code": "PHARMACY_PRESCRIPTION_REQUIRED",
    "message": "Prescription is required for Samuha KHA medicines.",
    "message_ne": "समूह ख औषधिका लागि प्रेस्क्रिप्सन आवश्यक छ।",
    "details": [{ "field": "lines[2].prescription_id", "code": "required" }],
    "request_id": "01J…"
  }
}
```

### 4.4 Status codes
`200` ok · `201` created · `202` accepted (async job) · `204` no content · `400` validation · `401` unauthenticated · `403` forbidden / `FEATURE_NOT_ENTITLED` / `TENANT_READ_ONLY` · `404` not found (also for other-tenant ids) · `409` version conflict / state conflict · `412` precondition failed · `422` domain rule violation · `423` locked period · `429` rate limited · `5xx` server.

### 4.5 Error code catalogue
Codes are `UPPER_SNAKE`, prefixed by module, registered in `shared/errors/catalogue.py` with en/ne messages and docs. CI fails on unregistered codes.

## 5. Frontend

- **App Router**; server components for shells/static; client components for interactive forms/tables/POS.
- Data: **only** via generated `@npms/api-client` hooks. No ad-hoc `fetch` to backend.
- Forms: `react-hook-form` + `zod`; server errors mapped to fields via `details[].field`.
- Tables: `@npms/data-table` (implements [MASTER] list contract). Do not build one-off tables.
- UI: only `@npms/ui` primitives (shadcn-based). New primitives go to the package with a Storybook story.
- Styling: Tailwind utilities + design tokens; no inline hex colours; dark mode supported.
- State: server state → TanStack Query; local UI state → component/Zustand (POS only); no Redux.
- Gating: wrap routes & actions in `<Feature>` / `<Can>`; backend remains authoritative.
- i18n: no user-visible literal strings; `t('…')` everywhere; numbers/dates via `@npms/i18n` formatters (lakh grouping, BS dates).
- Accessibility: every interactive element keyboard-reachable; visible focus; labels; `aria-live` for POS totals/alerts.
- Performance: route-level code splitting; virtualized lists > 200 rows; debounce search 150 ms; images via `next/image`.

## 6. Testing

| Layer | Tooling | Must cover |
|-------|---------|-----------|
| Backend unit | pytest, hypothesis | services, rules, money/tax/numbering properties |
| Backend API | pytest + DRF client | permission matrix, validation, **tenant isolation** |
| Frontend unit | Vitest + Testing Library | components, hooks, formatters |
| E2E | Playwright | critical journeys per module (POS bill, GRN, return, narcotic sale, import) |
| Contract | recorded fixtures | every integration adapter |
| Performance | k6 / Locust | X-PERF targets |

Test names describe behaviour: `test_kha_item_without_prescription_is_rejected`.

## 7. Logging, metrics, tracing

- Log JSON with: `timestamp, level, event, request_id, tenant_id, user_id, branch_id, device_id, module`.
- **Never log**: passwords, tokens, full phone/national IDs, prescription images, diagnosis text.
- Metrics naming: `npms_<area>_<metric>_<unit>` e.g. `npms_sync_push_duration_seconds`.
- Every Celery task and integration call is a traced span.

## 8. Documentation

- Every module has `README.md` (purpose, manifest summary, key flows, settings, events).
- Architectural changes → ADR in `docs/adr/`.
- User-facing changes → changelog entry (en + ne summary) in PR description section "Release note".
