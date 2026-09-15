# Architecture — Nepal e-Health Platform (starting with NPMS)

> Status: **Draft v0.1** · Owner: Platform team · Last updated: 2026-09-15
> Companion documents: [CHECKLIST.md](CHECKLIST.md) · [COMPLIANCE_REGISTER.md](COMPLIANCE_REGISTER.md)

---

## 1. Vision & Guiding Principles

Build **one multi-tenant e-health platform** where *Pharmacy* is the first vertical, and *Warehouse / Wholesale, Hospital, Clinic, Dental, Lab* are added later as **modules** on the same kernel — without forks, rewrites, or per-customer customization.

| # | Principle | What it means in practice |
|---|-----------|---------------------------|
| P1 | **Kernel → Core → Modules** | Tenancy, auth, RBAC, audit, entitlements live in the kernel. Patients, products, inventory, sales, accounting live in shared core. Pharmacy/Clinic/Dental only add domain behaviour. |
| P2 | **Regulation as configuration** | Tax rates, drug schedules, register formats, invoice fields, retention periods are data (versioned rules), not `if` statements. |
| P3 | **Offline is a first-class mode** | POS and dispensing must work with no internet for days. Sync is designed, not bolted on. |
| P4 | **Nothing is ever deleted** | Financial and regulatory records are immutable; corrections are reversal documents (credit note, stock adjustment, void). |
| P5 | **Entitlement-driven UI & API** | Every endpoint and every screen declares the module/feature/permission it needs. Plans turn them on/off. |
| P6 | **Configuration over customization** | Per-tenant settings, templates, workflows — never tenant-specific code branches. |
| P7 | **Boring, proven tech** | Django + PostgreSQL + Redis + Celery; Next.js + shadcn/ui + Tailwind. |
| P8 | **Data residency: Nepal** | Primary production data hosted in Nepal; backups geo-redundant within compliance limits. |

---

## 2. Tech Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Backend language | Python 3.12+ | |
| Web framework | Django 5.x + Django REST Framework | `drf-spectacular` for OpenAPI 3.1 |
| Async / realtime | Django Channels (ASGI) + Redis | Live dashboards, POS queue, notifications |
| Background jobs | Celery + Redis (broker) + `django-celery-beat` | CBMS sync, reminders, reports, imports |
| Database | PostgreSQL 16 | RLS, `pg_trgm`, partitioning for large ledgers |
| Search | PostgreSQL `pg_trgm` + `unaccent` (v1) → Meilisearch/OpenSearch (when >1M SKUs/tenant) | Medicine search < 1 s |
| Cache | Redis | Entitlement cache, sessions, rate limits |
| Object storage | S3-compatible (MinIO on-prem / S3-compatible cloud) | Prescriptions, attachments, exports |
| Frontend | Next.js (App Router) + TypeScript | pnpm + Turborepo monorepo |
| UI kit | shadcn/ui + Tailwind CSS + Radix | Shared `@npms/ui` package |
| Data fetching | TanStack Query + generated client (Orval from OpenAPI) | Types never hand-written |
| Forms | react-hook-form + zod | Zod schemas generated from OpenAPI where possible |
| Tables | TanStack Table | Server-side pagination/sort/filter, column chooser, export |
| Offline store | IndexedDB via Dexie + Service Worker (Workbox/Serwist) | POS, dispensing, stock lookup |
| Desktop shell | Tauri (Phase 2 of POS) | ESC/POS printing, cash drawer, scanner, local DB durability |
| Mobile | PWA first → React Native/Expo (owner app, delivery app) | |
| i18n | `next-intl` (frontend), Django i18n (backend) | Nepali (ne-NP) + English (en) |
| Auth | Session + JWT (short-lived access / rotating refresh) for API clients; TOTP 2FA; device binding for POS | |
| Observability | Sentry, OpenTelemetry → Prometheus/Grafana, Loki | |
| CI/CD | GitHub Actions → container registry → Docker Compose (early) → Kubernetes (scale) | |
| IaC | Terraform (cloud) + Ansible (on-prem appliance) | |

---

## 3. Layered Module Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  VERTICAL MODULES (sellable)                                             │
│  pharmacy · pharmacy_compliance · wholesale · hospital_pharmacy ·        │
│  warehouse · clinic · dental · hospital(HMS) · lab · omnichannel · ai    │
├──────────────────────────────────────────────────────────────────────────┤
│  SHARED CORE DOMAIN (reused by every vertical)                           │
│  organizations/branches · parties(customers/suppliers) · patients(MPI) · │
│  practitioners · catalog(items) · inventory(batches, ledger) ·           │
│  sales · purchasing · pricing · tax · payments · accounting(GL) ·        │
│  documents · notifications · numbering · import/export · reporting       │
├──────────────────────────────────────────────────────────────────────────┤
│  KERNEL (never sold separately, always on)                               │
│  tenancy · identity/auth · RBAC · audit · module registry ·              │
│  entitlements/feature flags · settings · files · jobs · webhooks ·       │
│  i18n/BS calendar · API conventions · offline sync protocol              │
├──────────────────────────────────────────────────────────────────────────┤
│  CONTROL PLANE (platform owner only — separate app & auth)               │
│  tenants · plans/pricing · modules/features · subscriptions & billing ·  │
│  platform accounting · CRM/leads · tasks · help desk · analytics ·       │
│  policies/legal · releases/updates · announcements · system health       │
└──────────────────────────────────────────────────────────────────────────┘
          INTEGRATIONS (adapters): IRD CBMS · eSewa · Khalti · Fonepay ·
          ConnectIPS · SMS gateways · WhatsApp Cloud API · HL7/FHIR ·
          Distributor EDI · Temperature loggers · SSF/HIB insurance
```

### Dependency rules (enforced by `import-linter` in CI)

1. `kernel` imports nothing from `core`, `modules`, `control`.
2. `core` imports only `kernel`.
3. `modules/*` import `kernel` + `core`; **never another module directly** — cross-module interaction goes through domain events or a published service interface declared in the module manifest.
4. `integrations/*` are adapters; domain code calls them through ports (interfaces) so they can be mocked and swapped.
5. `control` may read kernel tables (tenants, subscriptions) but never tenant business data except through audited support tooling.

---

## 4. Multi-Tenancy

### 4.1 Model: Pooled database, row-level isolation (default) + Silo option (enterprise)

| Option | Verdict |
|--------|---------|
| Schema-per-tenant (`django-tenants`) | ❌ Rejected as default — migrations are O(tenants); thousands of small pharmacies make deploys slow and risky. |
| DB-per-tenant | ✅ Offered only as **Silo tier** (large hospitals, chains wanting isolation, on-prem). |
| **Shared schema + `tenant_id` + PostgreSQL RLS** | ✅ **Default.** One migration run, cheap tenants, RLS as defence-in-depth against ORM mistakes. |

### 4.2 Implementation

- Every tenant-owned model inherits `TenantScopedModel` (`tenant_id UUID NOT NULL`, indexed; composite indexes always start with `tenant_id`).
- Default manager auto-filters by the current tenant from a context var; unscoped access requires `Model.all_tenants` and is lint-flagged.
- PostgreSQL RLS policy on every tenant table: `USING (tenant_id = current_setting('app.tenant_id')::uuid)`.
- Middleware sets `SET LOCAL app.tenant_id = ...` inside the request transaction (`ATOMIC_REQUESTS=True`) — safe with PgBouncer transaction pooling.
- Celery tasks carry `tenant_id` in headers; a task base class restores context.
- Tenant resolution order: custom domain → subdomain (`{slug}.app.<domain>`) → `X-Tenant` header (desktop/mobile, validated against token claims).
- Automated **cross-tenant leak test suite** runs on every PR (create 2 tenants, attempt every endpoint with the other tenant's IDs → must 404).

### 4.3 Organisation hierarchy inside a tenant

```
Tenant (customer account, billing unit)
 └── Legal Entity  (PAN/VAT number, IRD registration)          1..n
      └── Branch / Outlet (premises, DDA licence, invoice series) 1..n
           └── Location (counter, store room, rack, cold room, ward, warehouse bin) 1..n
                └── Device (POS terminal / desktop install, number-range holder) 0..n
```

- Invoice numbering: per **Branch × Fiscal Year × Document Type × (Device range)**.
- Users are tenant members with role assignments scoped to *tenant / legal entity / branch*.
- One human can belong to multiple tenants (e.g., a pharmacist doing locum) — identity is global, membership is per tenant.

---

## 5. Module & Entitlement System

### 5.1 Module manifest

Each Django app that is a sellable unit ships `module.py`:

```python
MODULE = ModuleManifest(
    code="pharmacy",
    name={"en": "Retail Pharmacy", "ne": "खुद्रा फार्मेसी"},
    version="1.0.0",
    depends_on=["core.catalog", "core.inventory", "core.sales", "core.purchasing"],
    features=[
        Feature("pharmacy.pos", kind="boolean"),
        Feature("pharmacy.narcotic_register", kind="boolean"),
        Feature("pharmacy.offline_pos", kind="boolean"),
        Feature("pharmacy.sku_limit", kind="limit", unit="skus"),
        Feature("pharmacy.sms_credits", kind="quota", unit="sms/month"),
    ],
    permissions=["pharmacy.dispense", "pharmacy.override_fefo", "pharmacy.narcotic.view", ...],
    nav=[NavItem(...)],               # consumed by frontend
    settings_schema=PharmacySettings, # pydantic/JSON-schema, rendered as settings UI
    events_published=["pharmacy.sale.completed", ...],
    events_consumed=["core.inventory.batch_recalled", ...],
    data_retention={"narcotic_register": "P10Y"},  # ISO-8601 durations, per rule set
)
```

On startup the **Module Registry** syncs manifests into kernel tables (`Module`, `Feature`, `Permission`) so the control plane can attach them to plans.

### 5.2 Entitlement resolution

```
effective(feature, tenant) =
      module_installed(tenant, feature.module)
  AND dependencies_satisfied
  AND ( plan_version.grants(feature)  OR addon.grants(feature)  OR tenant_override.grants(feature) )
  AND NOT global_kill_switch(feature)
  AND rollout_rule(feature).matches(tenant)      # % rollout, allow-list, beta cohort
  AND subscription.status in {trialing, active, grace}  # else read-only mode
```

- Resolved per tenant, cached in Redis (`entitlements:{tenant_id}:{version}`), invalidated on any plan/subscription/flag change via event.
- Backend: `permission_classes = [HasFeature("pharmacy.narcotic_register"), HasPerm("pharmacy.narcotic.view")]`.
- Limits/quotas: checked at write time (e.g., creating the 6th branch), usage counters in `UsageMeter`.
- Frontend: `GET /api/v1/me/context` returns tenant, branches, permissions, features, limits, nav → `<Feature code>` / `<Can perm>` guards and nav generation.

### 5.3 Subscription lapse / downgrade policy (non-negotiable)

| State | Behaviour |
|-------|-----------|
| Trial ending | Banner T-7, T-3, T-1 |
| Payment overdue | **Grace** (configurable, default 15 days): full access + banners |
| Suspended | **Read-only**: no new sales/purchases; *all* regulatory registers, invoices, and reports remain viewable & exportable |
| Cancelled | Read-only for retention window; full data export offered; hard delete only after statutory retention, with owner confirmation and audit |
| Downgrade removes a module | Module becomes read-only; data preserved; re-enable restores fully |

Rationale: a pharmacy must always be able to produce its narcotic register and tax invoices to DDA/IRD, regardless of billing status.

---

## 6. Data Design Conventions

| Concern | Convention |
|---------|-----------|
| Primary keys | UUIDv7 (time-ordered, generated client-side for offline docs) |
| Human numbers | Separate `number` field from Numbering Service (e.g., `INV-KTM01-2083/84-000123`) |
| Money | `Decimal` — `NUMERIC(18,4)` rates/cost, `NUMERIC(18,2)` totals; never float; currency code on every amount |
| Quantities | `NUMERIC(18,3)` in **base unit** (tablet/ml/g); pack conversions in `ItemUnit` |
| Dates | Stored in UTC (timestamps) / ISO date; BS shown via `nepali-date` lib; fiscal year computed from BS (Shrawan 1 → Ashadh end) |
| Soft delete | Masters only (`is_active`, `archived_at`); **transactions are never deleted** |
| Immutability | Posted documents are locked; changes only via reversal/amendment documents |
| Audit | Append-only `AuditEvent` (actor, tenant, branch, device, IP, action, entity, before/after JSON diff, reason, request_id), monthly partitioned |
| Stock | Append-only `StockLedgerEntry` (item, batch, location, qty ±, cost, doc ref); balances are materialized & reconcilable |
| Accounting | Double-entry `JournalEntry`/`JournalLine` auto-posted from business documents via posting rules |
| Events | Transactional outbox table → Celery dispatcher → in-process handlers & webhooks |
| Large tables | Range partition by month: audit, stock ledger, journal lines, notifications, sync logs |

---

## 7. Offline-First POS & Sync Protocol

### 7.1 What works offline
Billing (cash/credit), returns, prescription capture (photos queued), Samuha KHA/KA checks, narcotic register entries, stock lookup, customer lookup (cached), receipt printing, day-end cash count.

### 7.2 What does not
Online payments needing gateway confirmation (queued as *pending verification* or blocked by setting), CBMS real-time push (queued), cross-branch stock view (stale data shown with timestamp).

### 7.3 Protocol
1. **Device registration**: each POS device is registered to a branch and receives a device credential.
2. **Snapshot + delta pull**: items, batches, prices, tax rules, customers, doctors, settings — versioned by `server_seq` cursor per tenant.
3. **Number ranges**: device leases invoice-number blocks (e.g., 500 numbers) per fiscal year; refilled when online at 20% remaining. *(Must be validated with IRD — see Compliance Register CR-IRD-06.)*
4. **Outbox push**: offline docs stored with client UUIDv7 + idempotency key; pushed in order; server responds per-doc `accepted | conflict | rejected`.
5. **Conflict rules**:
   - Stock can go negative only for docs created offline; server raises a **stock discrepancy task**, never rejects a legal sale already handed to a patient.
   - Price/master conflicts: server version wins for masters; the sale keeps the price actually charged (it is a legal document).
   - Narcotic register: server recalculates running balance; mismatches raise high-priority alert.
6. **Durability**: Tauri desktop keeps SQLite/IndexedDB with WAL; browser PWA requests `navigator.storage.persist()`; unsynced-doc counter always visible; blocking warning on logout/cache clear with unsynced docs.
7. **Fiscal-year boundary**: device must sync before Shrawan 1 rollover; hard stop for billing in new FY without a new number range.

---

## 8. Compliance Engines

| Engine | Responsibility |
|--------|----------------|
| **Tax engine** | Item tax category (VAT 13% / exempt / zero-rated), customer type (VAT-registered/consumer), line vs invoice rounding, amount-in-words (en/ne, lakh/crore), versioned rates with effective dates |
| **IRD e-billing** | Immutable invoices, cancel-via-credit-note, reprint counter with "Copy of Original", sales/purchase registers, materialized views, CBMS push with retry & reconciliation, audit log exports |
| **Drug rules engine** | Drug schedule (Samuha KA/KHA/GA + special flags) → required actions at billing (prescription required, register entry, pharmacist-only, max qty, record-keeping) — rules versioned with effective dates so DDA updates are data deployments |
| **Retention engine** | Per record type retention periods; legal-hold; export-before-purge |
| **Inspection packager** | Generates DDA inspection bundle (PDF + XLSX + attachments ZIP) from live data, signed with hash & timestamp |

---

## 9. Integration Adapters

All adapters implement: config per tenant (encrypted secrets), sandbox/production mode, health check, request/response log (redacted), retry with exponential backoff, dead-letter queue, manual replay from UI, metrics.

| Adapter | Direction | Notes |
|---------|-----------|-------|
| IRD CBMS | Out | Bills, returns; sync status per document; daily reconciliation |
| eSewa / Khalti / Fonepay (dynamic QR) / ConnectIPS | Out + webhook in | Payment intent → verify → settle; never trust client callback alone |
| SMS (Nepal gateways, e.g., Sparrow/Aakash — choose at Phase 0) | Out | DLR tracking, credits metering |
| WhatsApp Business Cloud API | Out + webhook | Template approval workflow, opt-in record |
| Email (SMTP/SES-compatible) | Out | |
| HL7 v2 / FHIR R4 | In/Out | Hospital module, e-prescriptions |
| Distributor ERP (EDI/REST) | In/Out | Catalog, stock, price, PO, invoice/ASN |
| Temperature loggers | In | CSV/USB import (v1), BLE/IoT (v2) |
| SSF / Health Insurance Board | Out | Claim line items (hospital module) |

---

## 10. Security Architecture

- Separate identity realms: **tenant users** vs **platform staff** (control plane) — different tables, domains, session cookies, and mandatory 2FA + IP allow-list for staff.
- RBAC: Role → Permission sets, scoped assignments (tenant/entity/branch); system roles (Owner, Admin, Pharmacist-in-charge, Pharmacist, Counter Staff, Store Keeper, Accountant, Auditor, DDA Inspector (read-only, time-boxed)) + custom roles.
- Sensitive action step-up: narcotic override, price override, void/credit note, stock adjustment, FEFO override → reason + optional supervisor PIN.
- Support impersonation: requires ticket reference, tenant-owner consent setting, time-boxed, banner shown to user, fully audited.
- Encryption: TLS 1.3; disk/volume encryption; field-level encryption (patient phone, national ID, diagnosis notes) with KMS-managed keys.
- Secrets: never in repo; Vault/SOPS; per-tenant integration secrets encrypted with envelope encryption.
- OWASP ASVS L2 as baseline; rate limiting; CSP; dependency & container scanning in CI.
- Privacy: consent records, purpose limitation, data subject export, aligned with Nepal's Individual Privacy Act 2075 (verify obligations — CR-PRIV-01).

---

## 11. Deployment Topologies

| Topology | Who | Shape |
|----------|-----|-------|
| **Cloud Pooled** | Most retail pharmacies, small chains | Shared cluster in Nepal DC; shared DB with RLS |
| **Cloud Silo** | Hospitals, large chains, distributors | Dedicated DB (and optionally dedicated workers) — same code, DB router by tenant |
| **On-Prem Appliance** | Poor connectivity hospitals / government | Docker Compose bundle on customer server; license file; update channel; optional cloud backup & control-plane heartbeat |
| **Hybrid Edge** | Chains with unreliable branches | Branch runs POS desktop offline-first, syncs to cloud |

Release channels: `edge` (internal) → `beta` (opt-in tenants) → `stable` → `lts` (on-prem, 12-month support). Database migrations follow **expand → migrate → contract** so any two adjacent versions run against the same schema (zero-downtime & safe rollback).

---

## 12. Repository Layout

```
/
├── backend/        Django project (kernel, core, modules, control, integrations)
├── frontend/       pnpm + Turborepo monorepo (web, console, portal, desktop, shared packages)
├── deployment/     Docker, Compose, Kubernetes/Helm, Terraform, Ansible, CI templates, runbooks
└── docs/           Architecture, checklist, compliance register, ADRs, API & user docs
```

See `backend/README.md`, `frontend/README.md`, `deployment/README.md` for detailed trees.

---

## 13. Architecture Decision Records (initial)

| ADR | Decision | Status |
|-----|----------|--------|
| ADR-0001 | Pooled multi-tenancy with RLS; silo as tier | Accepted (draft) |
| ADR-0002 | Kernel / Core / Modules layering with import-linter enforcement | Accepted (draft) |
| ADR-0003 | UUIDv7 PKs + separate human document numbers | Accepted (draft) |
| ADR-0004 | Offline POS via PWA + Tauri, outbox sync, leased number ranges | Proposed — pending IRD validation |
| ADR-0005 | OpenAPI-first; frontend client generated (Orval) | Accepted (draft) |
| ADR-0006 | Immutable transactional documents; reversal-only corrections | Accepted (draft) |
| ADR-0007 | Drug & tax rules as versioned data with effective dates | Accepted (draft) |
| ADR-0008 | Control plane as separate app + auth realm | Accepted (draft) |
| ADR-0009 | Read-only (never delete) on subscription lapse | Accepted (draft) |
| ADR-0010 | Monorepo with backend/frontend/deployment/docs | Accepted |

ADR files live in `docs/adr/NNNN-title.md` (template in `docs/adr/0000-template.md`).
