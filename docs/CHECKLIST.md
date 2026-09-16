# Master Build Checklist — Nepal e-Health Platform (Pharmacy First)

> **Version** 0.1 · **Date** 2026-09-15 · **Source** BRD v2.0 + architecture review
> Read first: [ARCHITECTURE.md](ARCHITECTURE.md) · [CONVENTIONS.md](CONVENTIONS.md) · [CONTROL_PLANE.md](CONTROL_PLANE.md) · [COMPLIANCE_REGISTER.md](COMPLIANCE_REGISTER.md)

---

## How to use this checklist

- `[ ]` open · `[x]` done · `[~]` in progress · `[-]` deliberately dropped (write reason inline)
- Each **Phase** has **Milestones (M)**. A milestone is closed only when every item **and** its *Exit Criteria* are met.
- **Priority tags:** `P0` must-have for the milestone · `P1` should-have · `P2` nice-to-have (may move to a later milestone).
- **The Foundation (Phases 0–3) is not optional and not rushed.** ~~No vertical-module code is merged until milestone **M3.4** is closed.~~
  **Relaxed 2026-09-16, deliberately.** The kernel is far enough along (tenancy, auth, RBAC, audit,
  entitlements, calendar, numbering) that continuing to build unseen infrastructure was adding
  risk rather than removing it. Core domain and pharmacy work now proceed in parallel with the
  control plane. What this trades away: plans, subscriptions and billing will exist only as
  entitlement grants until Phase 3 catches up, so **nothing may be sold to a real customer until
  M3.4 is closed** — the constraint moves from "do not build" to "do not sell".
- Every item that produces code must satisfy the **Definition of Done** (§0.2).
- Anything regulatory references a `CR-*` id from the Compliance Register — do not implement until that CR is ✅.

### 0.1 Standard contracts (referenced everywhere below)

To avoid "small things forgotten", every entity/screen **must** satisfy these contracts. When an item says *"[MASTER]"* or *"[DOC]"*, all bullets of that contract apply.

#### [MASTER] — Standard Master-Data Contract (items, suppliers, customers, doctors, …)
- [ ] List view: server-side pagination (page size 25/50/100/500), sort on every column, global search, per-column filters, saved filters/views per user, column show/hide/reorder/resize (persisted), density toggle, sticky header, row selection
- [ ] Empty state, loading skeleton, error state with retry, "no results for filter" state
- [ ] Create / Edit form: zod validation mirrored from API, field-level server errors, dirty-state leave warning, keyboard submit (Ctrl+Enter), Esc to cancel
- [ ] Duplicate detection on create (name / code / PAN / phone as relevant) with "view existing" link
- [ ] Detail page: summary header, tabs (overview, related transactions, attachments, notes, audit history)
- [ ] Archive / restore (no hard delete if referenced); hard delete only when never referenced + permission
- [ ] Bulk actions: archive, restore, assign tag, bulk edit selected fields, export selected
- [ ] **Import**: downloadable template (CSV + XLSX) with header comments & example rows; upload → column mapping UI (auto-match, save mapping) → dry-run validation → row-level error report (downloadable XLSX with error column) → partial/all-or-nothing option → background job with progress → import summary (created/updated/skipped/failed) → undo import (within 24h if no downstream usage); upsert key selectable; Nepali Unicode & Preeti-font legacy conversion warning
- [ ] **Export**: CSV, XLSX, PDF (current view / all matching filter / selected rows), choice of visible columns vs all columns, BS/AD date format option, large exports as async job with notification + download link expiring in 7 days, export action audited
- [ ] Print: print-friendly list & detail
- [ ] Attachments (S3), notes/comments with @mentions, tags
- [ ] Audit history tab (who/when/what changed, before → after)
- [ ] Permissions: view / create / edit / archive / import / export / view-cost (where applicable) — separately assignable
- [ ] Bilingual labels (en/ne); Devanagari-capable search
- [ ] API: list/retrieve/create/update/partial update/archive/restore + `?fields=` sparse fieldsets + `?expand=` + cursor pagination for sync + `updated_since` filter
- [ ] Tests: model, serializer, API permission matrix, tenant-isolation, import/export round-trip, e2e happy path

#### [DOC] — Standard Transaction-Document Contract (invoice, PO, GRN, return, transfer, adjustment, …)
- [ ] Lifecycle states defined & enforced (e.g., Draft → Submitted → Approved → Posted → Cancelled/Reversed); state machine unit-tested
- [ ] Number assigned from Numbering Service on the configured event (save vs post); gapless where legally required
- [ ] Posted documents immutable; corrections only via reversal/amendment document linked to original
- [ ] Draft auto-save; resume draft; discard draft (drafts may be deleted)
- [ ] Line editor: keyboard-first grid (Tab/Enter/arrow navigation, F-keys), add by scan/search, inline batch/expiry select, qty in pack/loose units, per-line discount, per-line tax display, running totals
- [ ] Header: branch, date (BS/AD), party, reference no., remarks, attachments
- [ ] Approval workflow hook (configurable thresholds), approval history
- [ ] Posting creates: stock ledger entries, journal entries, tax records, events — all in one DB transaction (or saga with compensation)
- [ ] Print templates (A4, A5, 80mm, 58mm) — configurable, bilingual, logo, QR, amount in words (en/ne)
- [ ] Share: PDF download, email, WhatsApp link, SMS link
- [ ] Reprint counter & "Copy of Original — N" watermark (tax documents)
- [ ] List view per [MASTER] list rules + status chips + date-range presets (today, yesterday, this week, BS month, fiscal year, custom)
- [ ] Export per [MASTER] export rules; register-format exports (e.g., sales book, purchase book)
- [ ] Import of historical/opening documents (where applicable) via import framework
- [ ] Audit trail of every state transition with reason
- [ ] Permissions: create / edit draft / submit / approve / post / cancel / reverse / backdate / view cost / reprint
- [ ] Backdating rules (setting: allowed days, requires permission, never across a closed period)
- [ ] Period-lock respected (cannot post in locked accounting period)
- [ ] Offline-capable flag (POS docs) follows sync protocol
- [ ] Tests: state machine, posting correctness (stock + GL balanced), reversal symmetry, concurrency (two users posting against last unit), numbering under concurrency

#### [REPORT] — Standard Report Contract
- [ ] Filters: date range (BS/AD presets), branch(es), plus report-specific; filters persisted in URL (shareable)
- [ ] Summary cards + table + chart where useful; drill-down to source documents
- [ ] Group by / subtotal options; totals row
- [ ] Export CSV / XLSX / PDF (with header: tenant, branch, filters, generated by, generated at, page x of y)
- [ ] Schedule report (daily/weekly/monthly) to email/WhatsApp
- [ ] Heavy reports run async with progress; cached result with "as of" timestamp
- [ ] Permission-gated; cost/margin columns hidden without `view-cost`
- [ ] Performance budget: < 3 s for 1 year of a single-branch data (p95)

#### [SETTING] — Standard Settings Contract
- [ ] Defined in module manifest `settings_schema` with defaults, type, validation, scope (tenant / legal entity / branch / user)
- [ ] Rendered automatically in Settings UI with description (en/ne) and "reset to default"
- [ ] Changes audited; sensitive settings require Owner role / step-up auth
- [ ] Settings export/import (clone configuration to another branch/tenant)

#### [INTEGRATION] — Standard Integration Contract
- [ ] Credentials stored encrypted per tenant; "test connection" button
- [ ] Sandbox / production toggle
- [ ] Request/response log (PII redacted), searchable, retention 90 days
- [ ] Retries with backoff, dead-letter queue, manual replay, bulk replay
- [ ] Health status visible to tenant admin and platform console
- [ ] Contract tests against recorded fixtures; mock server for local dev
- [ ] Feature-flagged; kill switch

### 0.2 Definition of Done (every code item)
- [ ] Code reviewed (1 approval; 2 for kernel, tax, narcotic, numbering, sync, auth)
- [ ] Unit + integration tests; coverage not decreased; critical domains ≥ 90%
- [ ] Tenant-isolation test added for any new tenant-scoped endpoint
- [ ] OpenAPI schema updated; frontend client regenerated; no TS errors
- [ ] Permissions & feature gates declared in manifest
- [ ] Audit events emitted for writes
- [ ] i18n keys added for en & ne (no hardcoded strings)
- [ ] Migrations are backward-compatible (expand/contract)
- [ ] Docs updated (API notes, user help snippet, changelog entry)
- [ ] Accessibility: keyboard reachable, labels, contrast (WCAG 2.1 AA)
- [ ] Observability: logs with request_id/tenant_id, metrics for new jobs/integrations
- [ ] Security: input validation, authz checked server-side, no secrets in code

---

## Phase overview & milestones

| Phase | Name | Milestones | Indicative duration |
|-------|------|-----------|---------------------|
| 0 | Discovery, Compliance & Product Definition | M0.1–M0.4 | 3–4 weeks (parallel with Phase 1) |
| 1 | Root Setup: Repository, Tooling, Environments, CI/CD | M1.1–M1.6 | 3 weeks |
| 2 | Kernel: Tenancy, Identity, RBAC, Audit, Modules, Entitlements | M2.1–M2.9 | 6–8 weeks |
| 3 | Control Plane (Platform Owner Console) | M3.1–M3.10 | 6–8 weeks (overlaps Phase 4) |
| 4 | Shared Core Domain | M4.1–M4.10 | 8 weeks |
| 5 | Pharmacy Retail MVP (online) | M5.1–M5.10 | 8 weeks |
| 6 | Offline POS & Desktop | M6.1–M6.4 | 4–5 weeks |
| 7 | IRD e-Billing, CBMS & Payments | M7.1–M7.5 | 4 weeks (+ IRD approval lead time) |
| 8 | Pharmacy Compliance Suite (DDA/CSDD/GSDP) | M8.1–M8.7 | 5 weeks |
| 9 | Pilot, Hardening & Commercial Launch | M9.1–M9.5 | 6 weeks |
| 10 | Patient Engagement | M10.1–M10.5 | 4 weeks |
| 11 | Pharmacy Chains (multi-branch) | M11.1–M11.4 | 4 weeks |
| 12 | Wholesale / Distributor & ERP-to-ERP | M12.1–M12.6 | 6 weeks |
| 13 | Hospital Pharmacy | M13.1–M13.5 | 6 weeks |
| 14 | Analytics & AI Intelligence | M14.1–M14.5 | 6 weeks |
| 15 | Omnichannel, Patient Portal & Mobile Apps | M15.1–M15.5 | 6 weeks |
| 16 | Future Verticals: Warehouse (WMS), Clinic, Dental, Lab, HMS | M16.x | Roadmap |
| X | Cross-cutting tracks (Security, QA, Performance, DR, Docs, Support, Legal, GTM) | continuous | continuous |

---

# PHASE 0 — Discovery, Compliance & Product Definition

## M0.1 Regulatory verification
- [ ] P0 Assign compliance owner; create shared evidence folder (scans of Gazette notices, DDA/IRD circulars)
- [ ] P0 Close every item in [COMPLIANCE_REGISTER.md](COMPLIANCE_REGISTER.md) marked blocking (CR-IRD-01, 04, 05, 06, 07; CR-DDA-01, 02, 06, 09, 12; CR-PRIV-01, 02)
- [ ] P0 Decide VAT treatment matrix (medicines exempt vs taxable categories) → seed tax categories
- [ ] P0 Obtain official CSDD 2024 document; transcribe 16 components / 121 indicators into structured YAML (`backend/modules/pharmacy_compliance/fixtures/csdd_2024.yaml`)
- [ ] P0 Obtain official Samuha KA/KHA/GA lists; decide source-of-truth & update process
- [ ] P0 Initiate IRD e-billing software approval inquiry (lead time is external — start now)
- [ ] P1 Meet DDA (or consultant) to validate digital narcotic register acceptability & inspection package format
- [ ] P1 Legal review: Electronic Transactions Act — digital signatures on registers/invoices
- [ ] P1 Payment gateway merchant model decision (per-tenant merchant vs aggregator) — CR-PAY-01
- [ ] P2 Insurance (SSF/HIB) integration specs collected

**Exit criteria:** blocking CRs ✅; tax matrix and drug schedule sources signed off.

## M0.2 Field research & personas
- [ ] P0 Visit ≥ 10 retail pharmacies (Kathmandu valley + 2 outside), 2 chains, 2 distributors, 1 hospital pharmacy
- [ ] P0 Record current workflows: purchase entry, bonus/scheme handling, loose sales, credit customers, day-end, narcotic book, expiry returns to supplier ("breakage/expiry claim")
- [ ] P0 Collect sample documents: supplier invoices (10+ formats), existing bills, narcotic register pages, DDA inspection reports
- [ ] P0 Catalogue hardware in use: printers (58/80mm, dot-matrix A4/A5), scanners, PCs (OS/RAM), internet type, UPS
- [ ] P0 Personas: Owner, Pharmacist-in-charge, Counter staff, Store keeper, Accountant, Distributor sales rep, Hospital pharmacist, DDA inspector, Platform support agent, Platform sales
- [ ] P1 Competitive teardown (hands-on trial where possible): Marg, Gofrugal, eVitalRx, local Nepali pharmacy software, Danphe EMR pharmacy — feature matrix + UX notes + pricing
- [ ] P1 Data migration sources: which legacy software/Excel formats are common → import adapters priority list
- [ ] P1 Language: which screens staff prefer in Nepali; legacy Preeti font data prevalence

**Exit criteria:** workflow maps & persona docs in `docs/research/`; migration source list prioritized.

## M0.3 Product definition
- [ ] P0 Finalize module catalogue with codes (see §Appendix A) and dependencies
- [ ] P0 Finalize plans (Starter / Standard / Professional / Enterprise / On-Prem) → module + feature + limit matrix (see [CONTROL_PLANE.md](CONTROL_PLANE.md) §4)
- [ ] P0 Pricing model: one-time licence + AMC **and** subscription (monthly/annual) — both supported by billing engine
- [ ] P0 MVP scope freeze for Phase 5 (list of included FR ids from BRD)
- [ ] P0 Non-functional targets signed off (see Track X-PERF)
- [ ] P1 Clickable prototype (Figma) of POS, purchase entry, narcotic register, owner dashboard, platform console → test with 5 pharmacists
- [ ] P1 Naming, brand, domain(s) (`.com.np` registration requires docs — start early), trademark search
- [ ] P2 Pricing page draft

## M0.4 Team, process & governance
- [ ] P0 Roles: Tech lead, backend ×2–3, frontend ×2, QA, DevOps (part-time early), product/compliance, designer
- [ ] P0 Working agreement: branching (trunk-based, short-lived branches), PR template, review rules, release cadence
- [ ] P0 Tooling accounts: GitHub org, project board, Sentry, domain registrar, DNS, email (transactional), password manager, cloud/DC provider
- [ ] P0 ADR process; first ADRs 0001–0010 written in `docs/adr/`
- [ ] P1 Security & data-handling policy for staff (no production data on laptops, least privilege)
- [ ] P1 Incident response & on-call policy draft

---

# PHASE 1 — Root Setup: Repository, Tooling, Environments, CI/CD

> "Stronger the root, better the project." Nothing here is skipped.

## M1.1 Repository & conventions
- [~] P0 Git init; `main` protected (PR required, status checks required, linear history, signed commits recommended) — **repo initialised & pushed; branch-protection rules still to be configured in GitHub settings**
- [x] P0 Root files: `README.md`, `.gitignore`, `.gitattributes` (LF normalization, binary types, `*.xlsx binary`), `.editorconfig`, `LICENSE` (proprietary), `SECURITY.md`, `CONTRIBUTING.md`, `CODEOWNERS`, `CHANGELOG.md`
- [x] P0 `docs/CONVENTIONS.md` approved (naming, API, commit, branching, error codes)
- [ ] P0 Conventional Commits + commitlint; PR title check — *convention documented; commitlint needs the root Node toolchain from M1.3*
- [~] P0 PR template (what/why, screenshots, migration notes, checklist from DoD); issue templates (bug, feature, compliance change, incident) — **incident template pending**
- [x] P0 Pre-commit hooks (`pre-commit` for Python, `lefthook` or husky for JS): format, lint, secrets scan (gitleaks), large-file guard, trailing whitespace, YAML/JSON validity — *JS hooks added with M1.3*
- [x] P0 Top-level task runner — **`tasks.py` (stdlib Python, no `make` needed on Windows)**: `setup`, `dev`, `test`, `lint`, `fmt`, `migrate`, `openapi`, `ci`, `infra-*`, `worker`, `beat`; `seed`/`client`/`e2e`/`build` added as those capabilities land
- [ ] P1 Dev container (`.devcontainer/`) for one-command onboarding
- [ ] P1 Renovate/Dependabot config (grouped, weekly, auto-merge patch for dev deps)

## M1.2 Backend skeleton (Django)
- [x] P0 Python 3.12, dependency management with `uv` (lockfile committed)
- [x] P0 Project layout per `backend/README.md` (`config/`, `kernel/`, `core/`, `modules/`, `control/`, `integrations/`, `shared/`)
- [x] P0 Settings split: `base`, `local`, `test`, `staging`, `production`; all config via env (`django-environ`); `.env.example` complete & documented; startup fails fast on missing required env
- [x] P0 PostgreSQL 16 connection (psycopg 3), `CONN_MAX_AGE`, `ATOMIC_REQUESTS=True`, `pg_trgm`, `unaccent`, `pgcrypto` extensions via migration
- [~] P0 UUIDv7 primary key field & base models: `UUIDModel`, `TimeStampedModel`, `BaseModel`, `ArchivableModel`, `VersionedModel` done — **`TenantScopedModel` lands in M2.1, `DocumentModel` in M4.5**
- [x] P0 Custom user model set before the first migration (`identity.User`, email **or** phone login, DB-level constraint) — *switching later is a painful migration, so it is done up front*
- [x] P0 DRF configured: default auth, permission (deny-by-default), pagination (page + cursor), filtering (`django-filter`), ordering, throttling, versioned URLs `/api/v1/`
- [x] P0 `drf-spectacular` OpenAPI at `/api/schema/`, Swagger & Redoc (open in non-prod, admin-only in prod); schema generation is warning-free in CI
- [x] P0 Standard error envelope & error code catalogue (see CONVENTIONS §API) — bilingual (en/ne), every code registered, unregistered codes fail loudly
- [~] P0 Structured JSON logging (`structlog`) with `request_id`, `user_id` + secret redaction — **`tenant_id`, `branch_id`, `device_id` bound in M2.1/M2.2**
- [x] P0 Health endpoints: `/healthz` (liveness, **never touches the DB** — `non_atomic_requests`, regression-tested), `/readyz` (DB, Redis, migrations applied; leaks no connection details), `/version` (git sha, build time, app version) — *storage check added when uploads land in M2.7*
- [~] P0 Celery app + beat + `django-celery-results`; task base class with retries/backoff + request-id propagation; queues: `default`, `critical`, `bulk`, `notifications`, `integrations` — **tenant context & idempotency keys in M2.1/M2.9**
- [x] P0 Channels/ASGI with Redis channel layer
- [~] P0 Storage abstraction (`django-storages`, S3/MinIO) configured & bucketed — **presigned upload/download and ClamAV scanning in M2.7**
- [~] P0 Email backend abstraction (console/Mailpit in dev, SMTP in prod) — **templated bilingual emails in M2.7**
- [~] P0 Code quality: `ruff` (lint + format), `mypy --strict`, `django-stubs`, `import-linter` layer contracts (5 contracts enforced in CI) — **`bandit` pending; `ruff` S-rules cover the basics meanwhile**
- [x] P0 Testing: `pytest`, `pytest-django`, `factory_boy`, `pytest-xdist`, `time-machine`, `hypothesis`; **tests run against real PostgreSQL as a non-superuser role without `BYPASSRLS`**, so RLS behaves as in production
- [x] P0 Project-integrity tests: no missing migrations, OpenAPI generates clean, custom user model active
- [ ] P0 Management commands: `seed_dev` (demo tenants, users, catalogue), `sync_modules`, `check_tenant_isolation`, `create_platform_admin` — *need the Phase 2 models first*
- [ ] P1 `django-debug-toolbar` / `silk` in local only; N+1 detection (`nplusone`) failing tests
- [ ] P1 Money & quantity value objects in `shared/` with property-based tests
- [ ] P1 Nepali date (BS↔AD) conversion library in `shared/nepali_calendar/` with data table (BS 1970–2100), fiscal-year helpers, Nepali numerals, amount-in-words (en: lakh/crore; ne: देवनागरी)

## M1.3 Frontend skeleton (Next.js monorepo)
- [ ] P0 pnpm workspaces + Turborepo; Node LTS pinned (`.nvmrc`, `packageManager` field)
- [ ] P0 Apps: `apps/web` (tenant app), `apps/console` (platform owner) — `apps/portal`, `apps/desktop` scaffolded later
- [ ] P0 Packages: `ui` (shadcn/ui components, theme tokens), `api-client` (Orval-generated from OpenAPI + TanStack Query hooks), `auth`, `i18n`, `nepali-date`, `forms` (RHF + zod helpers), `data-table` (TanStack Table wrapper implementing [MASTER] list contract), `config-eslint`, `config-typescript`, `config-tailwind`, `utils`
- [ ] P0 TypeScript strict; path aliases; ESLint (next, react-hooks, jsx-a11y, import order), Prettier + tailwind plugin
- [ ] P0 Tailwind + shadcn/ui init; design tokens (CSS variables) for light/dark; brand colours; Devanagari-capable font stack (e.g., Inter + Noto Sans Devanagari/Mukta); numeric tabular figures for tables
- [ ] P0 App shell: sidebar (generated from `/me/context` nav), top bar (tenant/branch switcher, BS date, sync status, notifications, user menu, language toggle, theme toggle), command palette (Ctrl+K), breadcrumbs
- [ ] P0 Auth flows UI: login, 2FA, forgot/reset password, session expiry modal, tenant selection
- [ ] P0 Global error boundary, 404/403/500 pages, toast system, confirm dialog, "unsaved changes" guard
- [ ] P0 `<Feature>`, `<Can>`, `<ModuleGate>` components + route middleware gating
- [ ] P0 i18n with `next-intl`: `en`, `ne`; ICU plurals; key extraction & missing-key CI check
- [ ] P0 Keyboard shortcut system (global registry, help overlay `?`)
- [ ] P0 Testing: Vitest + Testing Library (unit), Playwright (e2e) with seeded backend, MSW for component tests
- [ ] P1 Storybook for `packages/ui` with a11y addon; visual regression (Chromatic/Playwright screenshots)
- [ ] P1 Bundle analyzer & performance budgets (JS < 250KB gz initial for web app shell)
- [ ] P1 PWA baseline (manifest, service worker via Serwist) — full offline in Phase 6

## M1.4 Local development environment
- [~] P0 `deployment/compose/docker-compose.dev.yml`: **postgres (non-superuser app role via init SQL), redis, minio + bucket init, mailpit done** — pgbouncer, celery worker/beat, flower, backend/web/console containers, clamav & meilisearch profiles pending
- [~] P0 One command: `python tasks.py setup && python tasks.py infra-up && python tasks.py migrate && python tasks.py dev` → working stack — **seeded demo data pending (needs Phase 2 models)**
- [~] P0 Hot reload backend; `.vscode/settings.json` + recommended extensions — **`launch.json` debugger configs for Django/Celery/Next pending**
- [x] P0 Dev host ports moved off the defaults (PG 55432, Redis 56379, MinIO 59000/59001, Mailpit 51025/51026) so the stack coexists with other local projects, and avoid Windows reserved port ranges
- [ ] P0 Local subdomains for tenants (`*.localhost` or `lvh.me`) documented
- [ ] P0 Seed data: 3 demo tenants (retail single, chain with 3 branches, distributor), users for every role, 500 medicines with batches/expiries, doctors, customers, suppliers
- [ ] P1 Anonymized production-like dataset generator for performance tests (1M SKUs, 10M ledger rows)
- [ ] P1 Windows notes (WSL2, line endings, Docker Desktop resources)

## M1.5 CI/CD
- [~] P0 GitHub Actions workflows: **`backend.yml` done** (ruff, format, import-linter, mypy, missing-migration check, pytest on Postgres/Redis services with the non-superuser role, OpenAPI validation) — pending: `frontend.yml` (lint, typecheck, unit, build), `openapi.yml` (schema diff; fail if client not regenerated), `e2e.yml` (Playwright on compose stack), `security.yml` (gitleaks, pip-audit, pnpm audit, Trivy image scan, CodeQL/Semgrep)
- [ ] P0 Path filters & caching (uv, pnpm, turbo remote cache, docker layer cache)
- [ ] P0 Container images: multi-stage Dockerfiles (backend, worker, web, console), non-root user, distroless/slim base, healthchecks, SBOM (syft), image signing (cosign)
- [ ] P0 Image tagging: `sha`, `semver`, `channel`
- [ ] P0 Environments: `dev` (auto on main), `staging` (auto on release candidate), `production` (manual approval) — with GitHub Environments & protected secrets
- [ ] P0 Migration job runs before app rollout; rollback plan documented
- [ ] P0 Release automation: semantic version from commits, changelog generation, GitHub release, release notes draft pushed to Control Plane "Releases"
- [ ] P1 Preview environments per PR (ephemeral namespace) for frontend + backend
- [ ] P1 DB migration safety linter (`django-migration-linter`) — blocks non-backward-compatible ops

## M1.6 Infrastructure baseline
- [ ] P0 Choose hosting in Nepal (DC/cloud) meeting CR-PRIV-02; secondary region/DC for backups
- [ ] P0 Environments provisioned with IaC (Terraform where API exists; Ansible for VMs)
- [ ] P0 Network: private subnets for DB/Redis, bastion/VPN (WireGuard), firewall rules, DDoS/WAF at edge (Cloudflare or DC-provided)
- [ ] P0 DNS: `app.<domain>` (wildcard for tenants), `console.<domain>`, `api.<domain>`, `status.<domain>`, `docs.<domain>`; wildcard TLS (Let's Encrypt DNS-01 / cert-manager)
- [ ] P0 PostgreSQL: managed or self-hosted with Patroni; PgBouncer; pgBackRest (full weekly, diff daily, WAL continuous); PITR tested
- [ ] P0 Redis with persistence (AOF) & sentinel/replica
- [ ] P0 Object storage with versioning + lifecycle rules; separate buckets: `attachments`, `exports` (7-day expiry), `backups`, `static`
- [ ] P0 Secrets management (Vault or SOPS + age); rotation procedure documented
- [ ] P0 Observability: Sentry (backend + frontend, release tracking), Prometheus + Grafana dashboards (API latency, error rate, Celery queues, DB, sync lag), Loki logs, Uptime Kuma/status page, alert routing (email/SMS/Slack/Viber)
- [ ] P0 Backup restore drill documented & executed once before Phase 5 ends
- [ ] P1 Kubernetes (k3s/RKE2 or managed) + Helm charts when > 1 app node needed; until then Docker Compose + systemd + Caddy/Nginx on VMs
- [ ] P1 Cost dashboard

**Phase 1 exit criteria:** new engineer clones → running stack with seed data in < 10 minutes; CI green & required; staging deploy automated; backup/restore proven.

---

# PHASE 2 — Kernel

## M2.1 Tenancy
- [x] P0 Models: `Tenant` (slug, name en/ne, status, tier, default language, timezone, trial end, status reason/timestamp), `TenantDomain` (custom domain, verification token, one primary per tenant), `TenantMembership` (user ↔ tenant, status, default branch), `LegalEntity` (PAN + VAT-registered flag — **in Nepal the VAT number *is* the PAN**, so there is no second field), `Branch` (code, name en/ne, address FKs, ward, phone, **DDA licence number & expiry**, is_warehouse), `Location` (counter/store/rack/shelf/bin/cold room/fridge/freezer/locked cabinet/ward/OT/warehouse, parent, temperature zone, is_sellable) — *created_by / lead_id arrive with the control plane in M3.2*
- [~] P0 Nepal address master — **models + idempotent `import_geo` command + the 7 provinces (bilingual) shipped**; districts and local levels must come from an official CBS/MoFAGA file, not from memory (CR-GEO-01)
- [x] P0 Tenant context: middleware resolution (verified custom domain → subdomain → header, **header off by default until tokens carry a verified claim**), context var, `SET LOCAL app.tenant_id` (never session-level `SET`, which would leak across tenants under PgBouncer transaction pooling), RLS policies via a reusable migration operation
- [~] P0 DB roles: **app role without `BYPASSRLS` and not superuser, in dev, CI and production; tables set to FORCE row level security so the owning role cannot bypass its own policies; asserted by a test** — separate migration role and audited control-plane bypass role come with M3.1
- [~] P0 Tenant-aware managers (`objects` scoped, `all_tenants` explicit escape hatch that the database still constrains), querysets, admin (registry models only) — **serializer-level foreign-tenant FK rejection lands with the first tenant-scoped API in M4.x**
- [ ] P0 Celery tenant propagation; Channels groups namespaced by tenant
- [ ] P0 Cache keys namespaced by tenant; file storage prefix `tenants/{tenant_id}/...`
- [~] P0 **Tenant isolation test harness** (`backend/tests/test_tenant_isolation.py`, runs in CI): proves the role cannot bypass RLS, that **every** `TenantScopedModel` has an enforced policy (fails the build when a new one is added without it), and that reads, raw SQL, inserts, updates and deletes across tenants all fail — **endpoint auto-discovery is added once tenant-scoped endpoints exist**
- [~] P0 Tenant provisioning service (idempotent): tenant → legal entity → HQ branch → **default locations including the locked narcotics cabinet and a non-sellable quarantine** — owner invite, roles, settings, numbering, chart of accounts, tax categories and module install are appended as those subsystems land
- [~] P0 Tenant lifecycle services: **suspend (read-only) and reactivate done, with reason recorded and no data removed** — cancel, archive, full data export and purge pending
- [ ] P1 Silo tier: DB router selecting connection by tenant; provisioning of dedicated DB; migration runner across silos
- [~] P1 Custom domain onboarding — **model and verified-only resolution done**; CNAME verification flow and automatic TLS pending
- [ ] P2 Tenant sandbox/training copy (clone tenant with anonymized data for staff training)

## M2.2 Identity & authentication
- [x] P0 Global `User` (email **and/or** phone as login, name en/ne, language, status); `TenantMembership` (user ↔ tenant, status invited/active/disabled, default branch) — *avatar pending*
- [~] P0 Login with email/phone + password; Argon2 hashing; password policy (length ≥ 10) — **done, plus: the backend hashes even for a non-existent account so response timing is not an enumeration oracle, and a tenant address only admits its own active members** — breached-password list pending
- [ ] P0 Invitations (email/SMS link, expiry 72h, resend, revoke)
- [ ] P0 Password reset (email/SMS OTP), rate-limited, no user enumeration
- [~] P0 2FA: TOTP + single-use recovery codes (hashed like passwords, ambiguous characters excluded), enrol → confirm-with-live-code → codes shown once, disable and regenerate both require the password, **and an accepted code cannot be replayed within its validity window** — *role-based enforcement waits for M2.3; SMS OTP fallback pending; **`TwoFactorDevice.secret` is stored unencrypted — see X-SEC field-level encryption***
- [~] P0 Sessions: HttpOnly Secure SameSite cookies for web + CSRF bootstrap endpoint — **JWT access/refresh with reuse detection, session listing and revocation pending**
- [x] P0 Account lockout after repeated failures (per identifier **and** per IP, keyed on the identifier as typed so a lockout never confirms an account exists); `LoginAttempt` log with outcome, IP and user agent — *progressive delay and geo pending*
- [ ] P0 Idle session timeout (configurable per tenant; POS longer with quick PIN re-lock)
- [ ] P0 **Quick user switch on POS**: shared terminal, staff unlock with 4–6 digit PIN tied to their account (every sale attributed to real user)
- [ ] P0 Device registry: register POS/desktop device to branch (admin approval), device token, last seen, revoke
- [ ] P1 Step-up authentication (re-enter password/PIN/2FA) for sensitive actions
- [ ] P1 Supervisor override flow: second user enters PIN on same screen → recorded as approver
- [ ] P1 SSO (Google Workspace / Microsoft) for enterprise tenants; SAML/OIDC for hospitals (P2)
- [ ] P2 Passkeys (WebAuthn)

## M2.3 Authorization (RBAC + scopes)
- [x] P0 Permission registry (`<module>.<resource>.<action>`, bilingual labels, auto-discovered from each app's `permissions.py`) — *module manifests feed the same registry when they land in M2.5*
- [x] P0 `Role` (system vs custom, tenant-scoped), `RolePermission`, `RoleAssignment` (user, role, scope: tenant / legal entity / branch) with a DB constraint that the scope matches its target
- [x] P0 System roles seeded per tenant and re-synced idempotently: Owner, Administrator, Pharmacist-in-Charge, Pharmacist, Assistant Pharmacist, Counter Staff, Store Keeper, Purchase Officer, Accountant, Auditor, DDA Inspector, Delivery Staff. **Owner resolves to every permission and Auditor/Inspector to every read-only permission, so a new module cannot accidentally hand an inspector write access.** Built-in roles are not editable — clone to vary — so a release that adds permissions cannot silently overwrite local edits
- [ ] P0 Role editor UI: permission matrix grouped by module, search, clone role, compare roles, "who has this permission" view
- [~] P0 Server-side checks: **`RequireTenant`, `HasPermission` (view-declared codes) and an inline `RequirePermission(...)` factory; `branch_ids_for()` returns the branch limit for a permission** — automatic queryset scoping helpers arrive with the first branch-scoped resource in M4.x
- [ ] P0 Field-level visibility: cost price, margin, supplier rates, patient diagnosis — permission-gated in serializers
- [x] P0 Professional qualification gates: `UserCredential` (council, number, expiry, verified_by) with a **credential requirement declared on the permission itself, so no role configuration can let an unregistered person do a pharmacist-only action**; an unverified or expired registration counts for nothing — *document upload pending*
- [~] P0 `/api/v1/me/context` endpoint — **user, tenant, memberships, branches and server time done**; permissions and features are present but empty until M2.3/M2.5; limits, nav, settings subset, BS date and fiscal year pending
- [x] P1 Temporary access grants (expiring role assignment) — used for inspectors & locum pharmacists
- [ ] P1 Permission change audit & monthly "access review" report for owners
- [ ] P1 Cache the resolved permission set — **currently computed per check on purpose**: an earlier per-user memo leaked one tenant's permissions into another. Belongs with the M2.5 entitlement cache, where invalidation is explicit

## M2.4 Audit & activity
- [~] P0 `AuditEvent` append-only — **enforced by database triggers on UPDATE, DELETE *and* TRUNCATE** (row triggers do not fire for TRUNCATE, so it needs its own), plus row-level security. **Monthly partitioning deferred**: it is a retention and volume concern, introduced later by a table swap, and the correctness-critical properties are in place now
- [~] P0 Capture via the service layer: `record_create` / `record_update` produce field diffs, values stay readable (Decimal as text, never float), and secret-looking fields are recorded as changed without revealing either value — **a save that changed nothing records nothing**. *Opt-in model mixin for automatic capture pending*
- [~] P0 Explicit business audit events — the full action vocabulary is defined (login, export, print, reprint, override, void, permission change, settings change, impersonation start/end, view-sensitive); **permission changes are wired up**, the rest are wired as each flow is built
- [~] P0 Hash-chaining per tenant with the chain head row-locked while appending, so concurrent writers cannot claim the same position; `verify_chain()` detects an altered entry, a forged entry, and a gap, and reports where — **daily off-database anchor hash pending**
- [ ] P0 Audit viewer UI (tenant admin): filters (user, entity, action, date, branch, device), export per [REPORT]
- [ ] P0 Entity "History" tab component reused across all detail pages — *`history_for(instance)` backs it*
- [ ] P1 Audit retention policy per tenant plan (min statutory) — *needs the partitioning above, since the triggers rightly block deletion*
- [ ] P1 Suspicious activity rules (e.g., many voids, after-hours narcotic sales, bulk export) → alerts to owner

## M2.5 Module registry, entitlements & feature flags
- [x] P0 `ModuleManifest` / `FeatureSpec` dataclasses declared in each app's `module.py`, discovered at startup; `sync_modules` command **and** a `post_migrate` hook write the `Module` and `Feature` tables, so every environment including the test database reflects the manifests as they are now rather than replaying an old data migration. **Nothing is deleted on sync**: a feature dropped from the code keeps its row and is reported, because removing it would cascade away the grants recording what customers bought
- [x] P0 Dependency graph validation — missing dependency and circular dependency both fail **at startup**, not at install time when it would be a customer's problem; install resolves dependencies first
- [x] P0 `TenantModule` (installed, enabled, config, disabled reason) and `FeatureGrant` (value, source, reason, expiry, granted_by) — *uninstall-blocked-if-dependents pending; disable is the supported path and keeps the data*
- [x] P0 Entitlement resolver: **plan sets the base, add-ons add to it, an override replaces the result outright**, expired grants stop counting, a disabled module hides its features while the grants wait. Cached by version token rather than key deletion, so a stale answer is never *read* — a grant or revocation takes effect on the next request
- [~] P0 Limits & quotas: `UsageMeter` model, `require_capacity()` / `remaining()` helpers, and **the branch ceiling enforced in the service layer so it holds however a branch is created** — quota consumption, 80% soft warnings and per-feature hard-limit behaviour pending
- [x] P0 Global feature flags: kill switch, percentage rollout with **stable per-account bucketing** (raising the percentage only ever adds accounts; a rollout that reshuffled on each deploy would be an outage), allow-list, deny-list, scheduled window
- [~] P0 Read-only mode: `TENANT_READ_ONLY` enforced for suspended accounts (M2.1); **`MODULE_NOT_ENABLED` and `FEATURE_NOT_ENTITLED` available as DRF permission classes** — applied per endpoint as modules are built
- [ ] P0 Frontend consumption: nav generation, route guard, component guards, upgrade prompts — *`/me/context` already returns `features` and `limits` for this*
- [ ] P1 Module settings schema rendering ([SETTING])
- [ ] P1 Module lifecycle hooks: `on_install`, `on_enable`, `on_disable`, `on_upgrade(from, to)`, `on_uninstall` (data retained)

## M2.6 Settings, numbering, calendar, localization
- [ ] P0 Settings service with scopes (platform default → plan default → tenant → legal entity → branch → user) and typed access
- [x] P0 **Numbering Service**: one series per branch × document type × fiscal year; pattern tokens `{TYPE}` `{BRANCH}` `{FY}` `{FY_SHORT}` `{BS_YYYY}` `{SEQ:6}` validated on registration (a pattern with no `{SEQ}`, or two, is rejected); **sequential via `SELECT FOR UPDATE` on the counter row**; device range leasing for offline billing, with the series skipping past a lent block so server and device can never collide; **fiscal-year rollover to 1 on Shrawan 1, and a backdated document still uses its own year's series**; preview without consuming; series creation and every lease audited; **pattern and counter frozen once a number has been issued**, because renumbering would reuse numbers that documents already carry. Document types are registered in code like permissions, so a typo cannot silently start a second series
- [ ] P0 Numbering: assign at **post**, never at draft — an abandoned draft that took a number leaves a gap. To be enforced by each document's state machine as it is built (M4.7)
- [ ] P0 Numbering: releasing a partly used leased block leaves a deliberate gap in the branch's run. **Blocked on CR-IRD-06** — IRD must confirm leased ranges are acceptable before this is used in a real pharmacy
- [~] P0 Fiscal year (BS-based, Shrawan 1 – Ashadh end): **`FiscalYear` with `2082/83` and `8283` labels, correct month-to-year attribution, and Gregorian bounds** — the stored period list and period locks arrive with accounting (M4.10)
- [~] P0 **Bikram Sambat engine: conversion both ways, a table loader, and validators** (month lengths 29–32, years 365–366, consecutive years, and a new-year drift check that catches accumulated errors). **No table is bundled on purpose** — the month lengths are published, not computed, and one wrong day shifts invoice dates and fiscal years. Supply a verified table via `BACKEND_BS_CALENDAR_FILE`; check it with `manage.py validate_bs_calendar` (CR-CAL-01). *Date pickers, per-user display preference and `_bs` fields in API responses still to come*
- [x] P0 Number formatting: South Asian grouping (1,00,000 not 100,000), Devanagari numerals, NPR with `रू`, half-up money rounding, and **amount-in-words in lakh and crore for tax invoices** — *Nepali wording needs a native reviewer before it is written*
- [ ] P0 Translations workflow: key files per module, translator-friendly export/import (XLSX/PO), missing-translation report
- [ ] P1 Nepali typing aids: Romanized → Devanagari input (Nepali unicode transliteration) in name fields; Preeti → Unicode converter for imports
- [ ] P1 Public holidays calendar (Nepal) per fiscal year — used by reminders, SLAs, reports

## M2.7 Files, notifications, jobs, events, webhooks
- [ ] P0 `FileObject` (tenant, owner entity generic FK, filename, mime, size, checksum, storage key, scan status, retention class); upload via presigned URL; image thumbnailing; PDF preview; max size per plan
- [ ] P0 Camera capture component (prescription photos) with compression & multi-page
- [ ] P0 Notification service: channels (in-app, email, SMS, WhatsApp, push), templates per event & language, user preferences, quiet hours, delivery status, retries, credits metering per tenant
- [ ] P0 In-app notification centre (bell, unread count, mark read, deep links), realtime via WebSocket
- [ ] P0 Transactional outbox + event dispatcher; event schema registry (versioned payloads); idempotent handlers
- [ ] P0 **Job centre UI**: user sees their imports/exports/reports jobs with status, progress, errors, download, cancel, retry
- [ ] P1 Outgoing webhooks for tenants (Enterprise): subscriptions per event, HMAC signing, retries, delivery log, replay
- [ ] P1 Public API keys for tenants (scoped, rotating, rate-limited)

## M2.8 Import / Export / Print framework (kernel-level, used by all modules)
- [ ] P0 Import framework: declarative `ImportSpec` per entity (fields, types, required, lookups by code/name, upsert key, validators, transformers, permission); pipeline stages (upload → parse CSV/XLSX/ODS → map → validate → preview → commit in batches → report); encoding detection (UTF-8/UTF-16/Windows-1252); BS/AD date parsing; decimal comma handling; row limit per plan; saved mappings; undo token
- [ ] P0 Export framework: declarative `ExportSpec`; streaming CSV; XLSX via openpyxl write-only mode; PDF via WeasyPrint templates; column selection; async above threshold (e.g., > 5,000 rows); signed expiring download URLs; export audit
- [ ] P0 Print/templating engine: HTML/CSS templates (Jinja/Django) → PDF (WeasyPrint) & thermal (ESC/POS commands via desktop agent/WebUSB); template variables catalogue; per-tenant template customization (logo, header, footer, fields toggle) with preview; versioned templates
- [ ] P0 Barcode/QR generation (Code128, EAN-13, QR) for labels & invoices
- [ ] P1 Label designer (shelf labels, batch labels, patient dosage labels) with printer profiles (A4 sheets, roll labels 38×25mm, 50×25mm)
- [ ] P1 Legacy software import adapters (per M0.2 priority list), starting with generic Excel templates

## M2.9 API conventions & developer experience
- [ ] P0 Implement CONVENTIONS §API: resource naming, error envelope, idempotency keys (`Idempotency-Key` header stored 24h), optimistic concurrency (`version` field / `If-Match` ETag → `409 CONFLICT`), cursor pagination, `updated_since`, sparse fields, expansions, bulk endpoints
- [ ] P0 Rate limiting per user/device/tenant/API key; `429` with `Retry-After`
- [ ] P0 Request correlation id propagated to Celery & logs & Sentry
- [ ] P0 OpenAPI annotations complete (examples, error responses, enums with descriptions)
- [ ] P0 Generated TS client & zod schemas; CI check for drift
- [ ] P1 API deprecation policy (`Deprecation`/`Sunset` headers), changelog per API version
- [ ] P1 Developer docs site (internal) generated from OpenAPI + guides

**Phase 2 exit criteria:** two demo tenants fully isolated (automated leak suite green); a dummy "hello" module can be installed/enabled/disabled via entitlement and appears/disappears in UI & API; import/export/print framework demonstrated on a sample entity; audit hash chain verifiable.

---

# PHASE 3 — Control Plane (Platform Owner Console)

> Full design in [CONTROL_PLANE.md](CONTROL_PLANE.md). Separate app (`apps/console`), separate auth realm (`PlatformStaff`), mandatory 2FA, IP allow-list, all actions audited.

## M3.1 Console foundation & staff administration
- [ ] P0 `PlatformStaff` identity (separate table), staff roles: Super Admin, Admin, Sales, Support Agent, Support Lead, Implementation/Onboarding, Finance, Compliance, Developer/Release Manager, Read-only Analyst
- [ ] P0 Staff permission matrix; staff invite/deactivate; enforced TOTP; session & device list; IP allow-list per role
- [ ] P0 Console shell (same `@npms/ui`), distinct colour theme to avoid confusion with tenant app
- [ ] P0 Console audit log (every read of tenant PII and every write)
- [ ] P0 Global search (tenants, leads, tickets, invoices, users by email/phone/PAN)
- [ ] P1 Staff working hours, availability, leave (for ticket assignment)

## M3.2 Tenant management
- [ ] P0 Tenant list [MASTER] with columns: name, slug, plan, status, tier, branches, users, MRR/ARR, AMC due date, last activity, health score, CBMS status, region, owner contact
- [ ] P0 Tenant detail: overview, subscription & invoices, modules & features (effective view with source: plan/addon/override/flag), usage vs limits, branches, users (read-only list), devices, integrations health, sync health (unsynced docs per device), tickets, tasks, notes, contacts, documents (contracts, KYC: PAN cert, DDA licence), audit, timeline
- [ ] P0 Actions: provision (wizard), change plan, add/remove addon, feature override (with reason & expiry), extend trial, suspend (with reason & notice), reactivate, cancel, export data, schedule purge (dual approval), reset owner 2FA (verified identity checklist), resend invite, rotate tenant integration secrets
- [ ] P0 **Support impersonation ("Login as")**: requires ticket id + reason, tenant consent setting honoured, time-box (30 min default), read-only mode default, write mode needs Support Lead approval, banner in tenant UI, full audit, tenant owner notified
- [ ] P0 Tenant KYC checklist: PAN/VAT certificate, DDA licence, pharmacist NPC certificate, company registration, agreement signed — document upload & verification status
- [ ] P1 Tenant health score (activity, sync errors, CBMS failures, tickets, payment status, NPS)
- [ ] P1 Bulk operations (bulk message, bulk flag enable for cohort)
- [ ] P1 On-prem licence management: generate signed licence file (tenant, modules, limits, expiry, hardware fingerprint), heartbeat status, update channel

## M3.3 Modules, features, plans & pricing
- [ ] P0 Module catalogue screen (from registry): version, dependencies, features, permissions, status (alpha/beta/GA/deprecated), docs link, which plans include it
- [ ] P0 Plan builder: `Plan` → `PlanVersion` (immutable once published) → included modules, features (boolean/limit/quota values), trial days, billing models (monthly/annual subscription; one-time licence + AMC), prices per currency (NPR default), per-branch/per-user/per-device add-on pricing, setup/implementation fees, discounts allowed
- [ ] P0 Add-ons catalogue (e.g., extra branch, SMS packs, AI module, Omnichannel, Cold-chain IoT, CBMS integration, ERP-to-ERP connector, extra storage)
- [ ] P0 Plan versioning & grandfathering: existing tenants stay on old version until migrated; bulk migration tool with preview of feature changes per tenant
- [ ] P0 Feature matrix comparison view (plans × features) & export
- [ ] P0 Coupons/promo codes (percent/fixed, validity, max redemptions, plan restrictions), partner/reseller discounts
- [ ] P0 Public pricing API (for website pricing page) — only published plans
- [ ] P1 Price books per segment (retail/chain/hospital/distributor) and per region
- [ ] P1 Plan change simulator (proration preview)

## M3.4 Subscriptions, platform billing & payments
- [ ] P0 `Subscription` (tenant, plan_version, addons, quantity, billing cycle, status trial/active/past_due/grace/suspended/cancelled, period start/end BS/AD, auto-renew, AMC due date)
- [ ] P0 Billing engine: invoice generation for subscriptions, licences, AMC, add-ons, setup fees; proration on upgrade/downgrade; credit notes; one-time invoices; usage-based charges (SMS)
- [ ] P0 **Platform's own IRD-compliant invoices** (we are also a VAT-registered business — software services taxable): numbering, VAT 13%, credit notes, sales register, CBMS sync for our own invoices
- [ ] P0 Payment collection: eSewa, Khalti, Fonepay QR, ConnectIPS, bank transfer (manual reconciliation with receipt upload & approval), cheque; payment links; receipts
- [ ] P0 Dunning: reminders T-7/T-3/T-0/T+3/T+7 (email/SMS/WhatsApp/in-app), grace → auto read-only → cancellation, with manual hold option
- [ ] P0 Tenant-side billing page: current plan, usage, invoices (download PDF), pay now, upgrade/downgrade request, payment method, billing contacts
- [ ] P1 Reseller/partner commissions
- [ ] P1 Revenue recognition schedule for annual/AMC (deferred revenue)

## M3.5 Platform accounting (our company books)
- [ ] P0 Chart of accounts for platform business; auto journal from platform invoices, payments, refunds, credit notes
- [ ] P0 Receivables ageing by tenant; collections dashboard
- [ ] P0 Expenses entry (hosting, SMS costs, salaries, marketing) with attachments & categories
- [ ] P0 Payables (vendors: DC, SMS provider, WhatsApp BSP), payment recording
- [ ] P0 Bank & wallet accounts, reconciliation (import statement CSV/XLSX)
- [ ] P0 Reports: P&L, balance sheet, trial balance, cash flow, VAT return summary, sales/purchase registers (IRD format), TDS summary — all [REPORT]
- [ ] P1 Export to accountant (Tally-compatible XML / XLSX)
- [ ] P1 Budget vs actual; unit economics (CAC, LTV, gross margin per tenant incl. SMS/infra cost)

## M3.6 CRM — leads & sales pipeline
- [ ] P0 Lead capture: website form API, manual entry, import [MASTER], WhatsApp/phone call log, referral source, campaign/UTM
- [ ] P0 Lead fields: business name, type (retail/chain/hospital/distributor/clinic/dental), branches count, contact persons, phone, email, address (province/district/municipality), current software, PAN, turnover band, interest modules, source, owner (staff), stage, score, expected close date, expected value
- [ ] P0 Pipeline Kanban (New → Contacted → Demo Scheduled → Demo Done → Proposal Sent → Negotiation → Won / Lost with reason) — configurable stages
- [ ] P0 Activities: calls, meetings, demos (calendar), emails, notes, follow-up reminders
- [ ] P0 Quotes/proposals: from plan builder, PDF with branding, validity, e-accept link
- [ ] P0 **Convert Won lead → Tenant** (pre-fills provisioning wizard, links lead ↔ tenant, triggers onboarding task template)
- [ ] P0 Duplicate detection (phone, PAN, business name fuzzy)
- [ ] P1 Territory/assignment rules (round robin, by district), sales targets & leaderboard
- [ ] P1 Demo tenant auto-provision for prospects (expires in 14 days, sample data)
- [ ] P1 Email/SMS campaigns to leads with opt-out

## M3.7 Tasks & onboarding projects
- [ ] P0 Tasks: title, description (rich text), assignee(s), watchers, due date, priority, status, labels, related entity (lead/tenant/ticket/release), checklist items, attachments, comments, time logged
- [ ] P0 Views: my tasks, team board (Kanban), list, calendar; filters; saved views
- [ ] P0 Task templates / playbooks: **Tenant Onboarding** (KYC collected → provisioned → master data import → hardware check → printer setup → training session 1 (counter) → training session 2 (pharmacist/compliance) → CBMS config → parallel run → go-live sign-off → 7-day check-in → 30-day review), AMC renewal, Churn-risk outreach
- [ ] P0 Recurring tasks; reminders & overdue notifications
- [ ] P1 Onboarding progress % visible on tenant detail and (optionally) to tenant owner
- [ ] P1 SLA timers on tasks linked to paid implementation packages

## M3.8 Help desk & support
- [ ] P0 Ticket channels: in-app widget (auto-attaches tenant, user, branch, app version, browser, current URL, recent errors, optional screenshot), email-to-ticket, phone call log, WhatsApp (via BSP webhook), console manual
- [ ] P0 Ticket fields: number, tenant, requester, category (billing/how-to/bug/data correction/compliance/integration/hardware/feature request), priority (P1 outage … P4), status (New/Open/Pending customer/Pending internal/Resolved/Closed), assignee, group, tags, linked tasks/bugs/releases
- [ ] P0 SLA policies by plan & priority (first response, resolution), business hours (Nepal, holidays calendar), breach alerts, pause on pending customer
- [ ] P0 Agent workspace: queue views, internal notes vs public replies, canned responses (en/ne), merge tickets, split, CC, attachments, satisfaction survey on close (CSAT)
- [ ] P0 **Data correction requests** workflow: tenant requests correction of posted document → support cannot edit; guides reversal flow or, for platform bugs, a dual-approved, fully audited data fix script with before/after record
- [ ] P0 Tenant-facing: my tickets list, reply, attach, reopen within 7 days
- [ ] P1 Knowledge base (articles en/ne, categories, search, video embeds, "was this helpful"), suggested articles while typing a ticket
- [ ] P1 Status page integration (incidents auto-linked to tickets, bulk notify affected tenants)
- [ ] P1 Remote-assist session notes & AnyDesk/RustDesk id field for hardware/printer issues
- [ ] P2 AI reply suggestions from KB

## M3.9 Policies, legal, announcements & communications
- [ ] P0 Policy documents: Terms of Service, Privacy Policy, Data Processing Agreement, SLA, Acceptable Use, Refund Policy — versioned (draft/published), bilingual, effective date
- [ ] P0 Acceptance tracking: on publish of material change, tenant owners/users must accept at next login (blocking modal) — record user, version, timestamp, IP
- [ ] P0 Announcements: in-app banners/modals targeted by plan/module/tenant/role/region, schedule window, dismissible or mandatory, en/ne
- [ ] P0 Maintenance windows: schedule, notify tenants (T-72h, T-24h, T-1h), in-app banner countdown, status page entry
- [ ] P1 Broadcast email/SMS/WhatsApp to tenant owners (with credit & opt-out compliance)
- [ ] P1 Regulatory update notices ("DDA added X to Samuha KHA effective …") pushed with changelog of rule-set versions

## M3.10 Releases, system updates, feature deployment & platform health
- [ ] P0 Release registry: version, channel, date, changelog (internal + customer-facing en/ne), migrations list, breaking-change flag, rollback plan, linked tickets
- [ ] P0 Feature flag console: create flag, link to module/feature, kill switch, rollout % slider, tenant allow/deny list, beta cohort management, schedule, audit, "who sees this" preview
- [ ] P0 Rule-set deployments (drug schedules, tax rates, CSDD indicators, invoice templates): upload/edit versioned rule set → validate → diff vs current → effective date → publish (dual approval for tax & narcotic rules) → notify tenants
- [ ] P0 Tenant-visible "What's new" feed per release
- [ ] P0 System health dashboard: API p95/p99, error rates, Celery queue depth & age, DB connections/replication lag/disk, Redis memory, storage usage, CBMS/payment/SMS/WhatsApp integration success rates, offline devices with oldest unsynced doc, failed jobs
- [ ] P0 Job & dead-letter management: view failed jobs across tenants, retry, discard with reason
- [ ] P0 On-prem update management: list on-prem installations, versions, last heartbeat, channel; publish update bundle (signed); force-update for critical security/compliance
- [ ] P1 Desktop (Tauri) auto-update channel management & staged rollout
- [ ] P1 Data migration tracker for long-running backfills (per tenant progress)

## M3.11 Platform analytics
- [ ] P0 Business KPIs: MRR, ARR, new/expansion/contraction/churned MRR, AMC revenue, collections, ARPA, trial→paid conversion, churn %, NRR, lead funnel conversion, sales cycle length
- [ ] P0 Product usage: DAU/WAU/MAU per tenant, feature adoption per module, invoices/day, GMV processed (aggregated), offline usage %, CBMS sync rates
- [ ] P0 Support KPIs: tickets by category, FRT, resolution time, SLA breach %, CSAT, tickets per tenant
- [ ] P0 Cohort & segment filters (plan, region, segment, signup month)
- [ ] P0 Exports & scheduled email digests ([REPORT])
- [ ] P1 Product event tracking pipeline (privacy-respecting, no PHI) → warehouse (ClickHouse/Postgres analytics schema)
- [ ] P1 Churn-risk & expansion signals feeding CRM tasks

**Phase 3 exit criteria:** a staff member can take a lead → quote → won → provision tenant → onboarding tasks → invoice & collect payment → enable/disable modules/features → handle a ticket with impersonation → publish a policy & release note — entirely in the console, all audited.

---

# PHASE 4 — Shared Core Domain

## M4.1 Parties (customers, suppliers, contacts)
- [ ] P0 `Party` with roles (customer, supplier, both), type (individual/business/hospital/government), name en/ne, PAN/VAT, VAT-registered flag, phones (multiple, primary), email, addresses (billing/shipping, Nepal address master), credit limit, credit days, opening balance (BS date), price list, tax exemption flag & certificate, tags, notes — [MASTER]
- [ ] P0 Contact persons per party
- [ ] P0 Party ledger/statement view (opening, transactions, running balance, ageing) — [REPORT] + share statement via WhatsApp/email
- [ ] P0 Walk-in customer default party per branch
- [ ] P1 Merge duplicate parties (with ledger re-pointing, audited)

## M4.2 Patients (Master Patient Index) & practitioners
- [ ] P0 `Patient`: MRN (per tenant), name en/ne, sex, DOB/age (estimated flag), phone, guardian/family link, address, allergies, chronic conditions, national ID/citizenship (encrypted, optional), NHIS/SSF number, consent flags (SMS/WhatsApp/data sharing), preferred language — [MASTER]
- [ ] P0 Family/household grouping (family ledger)
- [ ] P0 Patient ↔ Party link (billing) optional
- [ ] P0 `Practitioner` (doctor/dentist/health worker): name, council (NMC/NDC/NHPC/NPC), registration number (format validated), specialty, hospital/clinic, phone, verification status & method, verified_by — [MASTER]; quick-add from billing screen with "unverified" flag
- [ ] P0 Duplicate patient detection (phone + name + DOB fuzzy); merge with audit
- [ ] P1 Patient timeline component (purchases, prescriptions, counseling, reminders, ADRs) — reused by pharmacy, clinic, dental

## M4.3 Catalogue (items)
- [ ] P0 `Item` generic core: code/SKU, name en/ne, item type (medicine/device/consumable/cosmetic/general/service), category tree, brand, manufacturer, HS code, tax category, units (base unit + pack hierarchy e.g., tablet → strip(10) → box(10 strips)), barcode(s) per unit (multiple), is_batch_tracked, is_expiry_tracked, is_serial_tracked, shelf life, storage temperature zone, min/max/reorder levels per branch, default location per branch, images, status — [MASTER]
- [ ] P0 **Loose/partial sales** configuration per item (allow selling tablets from a strip; price per base unit derived)
- [ ] P0 Manufacturer & Brand masters [MASTER]
- [ ] P0 Category tree editor (drag-drop, bilingual)
- [ ] P0 Item variants/pack sizes as separate sellable units with shared stock in base unit
- [ ] P0 Bulk price update tool (by category/manufacturer/supplier, % or fixed, preview, schedule effective date)
- [ ] P0 Barcode label printing from item list (qty per label, template)
- [ ] P1 Item extension mechanism: modules attach typed extension tables (e.g., `pharmacy.MedicineProfile`) — no JSON dumping ground
- [ ] P1 Global catalogue (platform-maintained reference catalogue of Nepal-registered medicines) that tenants can **link** or **copy** from; tenant overrides; update notifications

## M4.4 Pricing
- [ ] P0 Price fields: purchase rate, cost (landed, incl. freight allocation), MRP, selling rate, wholesale rate; per batch where MRP differs by batch
- [ ] P0 Price lists (retail, wholesale, institutional, staff) with validity; party-specific prices
- [ ] P0 Discount rules: item/category/party/price-list, max discount % per role, bill-level discount, rounding rules (nearest 1/0.5/none)
- [ ] P0 **Schemes / bonus quantity** (e.g., 10+1 free) on purchase and sale; effective cost computation; scheme reporting
- [ ] P0 MRP enforcement: cannot sell above MRP (setting); DDA margin cap checks (CR-DDA-09) with warnings
- [ ] P1 Promotions (time-bound offers, buy X get Y, loyalty multipliers)

## M4.5 Inventory engine
- [x] P0 `Batch` (item, number, mfg/expiry dates, MRP **per batch**, cost, status: available/quarantined/expired/recalled/damaged). Stock is usable **up to and including** its printed expiry date
- [x] P0 `StockLedgerEntry` — **append-only in the database** (UPDATE, DELETE and TRUNCATE all refused); a mistake is corrected by a reversing entry that links to what it undoes, so the ledger shows the correction as well as the error. *Partitioning deferred with the audit table's, for the same reasons*
- [x] P0 `StockBalance` per (location, item, batch), row-locked while posting, written in the same transaction as the ledger entry so the two cannot disagree; `reconcile()` **reports** discrepancies rather than silently fixing them, because a wrong number means something wrote stock outside the service layer
- [~] P0 Allocation: **FEFO implemented and the default** — nearest expiry first, expired and quarantined stock never allocated, spilling across batches as needed. *FIFO and permissioned manual override pending*
- [x] P0 Expired stock is a hard stop for sales but can still be written off or returned, or it could never leave the shelf
- [ ] P0 Costing: moving weighted average (default) and batch-actual cost; cost used on sale posting
- [ ] P0 Negative stock policy (setting; offline exception rules)
- [ ] P0 Documents [DOC]: Stock Adjustment (reasons: damage, breakage, theft, expired write-off, count correction, sample; approval above value threshold), Stock Transfer (out → in-transit → received, partial receipt, discrepancy), Location Move (rack to rack), Opening Stock (import-driven)
- [ ] P0 **Physical stock count**: create count session (full/cycle/by category/by rack/by ABC class), freeze or live count mode, blind count option, mobile/tablet counting with scanner, multiple counters & recount, variance review, approval, auto adjustment posting, count sheet print & import
- [ ] P0 Expiry management: near-expiry buckets (configurable 90/60/30 days), auto status → expired at midnight, block sale of expired (hard), expiry return-to-supplier list
- [ ] P0 Quarantine workflow (hold/release with reason; quarantined excluded from sellable)
- [ ] P0 Stock inquiry screen: item → branches → locations → batches (qty, expiry, MRP), in-transit, reserved, on-order
- [ ] P0 Reports [REPORT]: stock summary, stock valuation (by cost method, as-of date), batch-wise stock, expiry report, near-expiry, dead/slow-moving (no sale in N days), stock ledger (item card), movement analysis, negative stock, ABC/XYZ analysis, reorder report
- [ ] P1 Reservations (for promise orders, online orders, hospital indents)
- [ ] P1 Serial number tracking (devices)

## M4.6 Purchasing
- [ ] P0 Supplier-item link (supplier codes, last rates, lead time, MOQ)
- [ ] P0 [DOC] Purchase Requisition/Indent (branch → HQ) — P1 for single store
- [ ] P0 [DOC] Purchase Order: from reorder suggestions / shortbook / manual; send PDF via email/WhatsApp; partial receipts; close short
- [~] P0 [DOC] Goods Receipt: supplier invoice number & date, batch, expiry, mfg date, quantity, **free quantity treated as stock that lowers the whole line's unit cost**, rate, MRP **per batch and converted to base units**, discount %, **freight spread across lines with the rounding difference absorbed so shares always add back**, and **VAT counted as cost only where it cannot be reclaimed**. Draft moves no stock; posting creates batches, moves stock and numbers the document in one transaction. Already-expired stock is refused unless confirmed deliberately, since it is sometimes taken in only to be returned. Cancelling reverses the movements and **keeps the number**, because a vanished document is a gap in the run. *Pending: rate-variance and MRP-change alerts, short-expiry warning, barcode printing on receipt, BS date entry*
- [x] P0 Duplicate supplier invoice number detection — the most common way stock gets doubled
- [ ] P0 3-way match PO ↔ GRN ↔ supplier invoice (variance tolerance setting)
- [ ] P0 [DOC] Purchase Return / Debit Note (expiry, damage, wrong item, rate difference); supplier claim tracking & settlement
- [ ] P0 Shortbook (digital "notebook" of items to order — added from POS when out of stock, auto-added below reorder level)
- [ ] P0 Supplier payments & ledger integration
- [ ] P1 Supplier invoice import (CSV/XLSX/PDF-table extraction) with item mapping memory per supplier
- [ ] P1 Landed cost for imports (customs, freight, insurance; multi-currency INR/USD with exchange rate per document)
- [ ] P1 Reports: purchase register (IRD format), supplier-wise, item-wise purchase, rate variance, pending POs, pending claims

## M4.7 Sales core
- [~] P0 Sales document types: **Tax Invoice built** — draft moves no stock; issuing numbers it, allocates **nearest-expiry batches first**, records **which batch each customer received** so a recall can be answered, and fixes the totals. **Prices come from the price printed on the batch** (falling back to the item for goods that are not batch-tracked), **selling above MRP is refused** because it is an offence, **tax is extracted from the shelf price** rather than added to it, the total rounds to whole rupees with the difference shown, and **reprints are counted so copies can be marked**. A bill that cannot be issued consumes no number, keeping the run gapless. *Pending: Abbreviated Invoice (CR-IRD-05), Credit Note, Quotation, Sales Order, Delivery Note, Proforma*
- [ ] P0 **Cancellation must be evidenced by a credit note** for IRD, not only by marking the invoice cancelled. Cancelling currently reverses the stock and keeps the number, which is correct but not yet sufficient for a tax audit (CR-IRD-04)
- [ ] P0 Credit sales with limit & overdue checks (block/warn/override by role)
- [ ] P0 Sales return: against original invoice (qty ≤ sold − returned), batch returns to stock or to quarantine/damaged, refund method, credit note numbering, reason codes, return without invoice (permission, limits)
- [ ] P0 **Cashier shift / day-end**: open shift with opening cash, cash in/out (petty expenses with category), close shift with denomination count (रू 1000/500/100/50/20/10/5/2/1), expected vs counted variance, per payment mode totals, Z-report print, supervisor sign-off; branch day-close
- [ ] P0 Hold/park bill & resume; multiple open bills
- [ ] P1 Sales order → invoice conversion; delivery challan

## M4.8 Tax engine
- [ ] P0 Tax categories & rates with effective dates (VAT 13%, exempt, zero-rated) — per CR-IRD-01 outcome
- [ ] P0 Line-level vs invoice-level computation rules; rounding to paisa; taxable vs non-taxable totals separated on invoice
- [ ] P0 Buyer PAN capture rules (threshold setting)
- [ ] P0 Sales & purchase VAT registers; VAT return helper (monthly)
- [ ] P0 Property-based tests: sum(lines) = totals, credit note reverses exactly
- [ ] P1 TDS on applicable purchases/expenses

## M4.9 Payments & receipts
- [ ] P0 Payment modes master (cash, card, eSewa, Khalti, Fonepay QR, ConnectIPS, bank transfer, cheque, credit, loyalty points, advance/deposit) per branch enabled
- [ ] P0 Split payments per invoice; change calculation; tips disabled
- [ ] P0 Gateway payment intents with status (pending/success/failed/expired), verification via server-side lookup, idempotent reconciliation, manual mark-paid with reference & permission
- [ ] P0 Customer receipts against outstanding invoices (allocation FIFO or manual), advances, refunds
- [ ] P0 Supplier payments, cheque register (PDC with due date reminders, bounced cheque handling)
- [ ] P1 Gateway settlement reconciliation import (statement upload)

## M4.10 Accounting (general ledger)
- [ ] P0 Chart of accounts template (Nepal SME), editable; account groups; cost centres = branches
- [ ] P0 Posting rules engine: document type → journal template (sales, returns, purchase, stock adjustment, payments, transfers between branches)
- [ ] P0 Manual journal voucher, payment voucher, receipt voucher, contra voucher [DOC]
- [ ] P0 Period close & lock; fiscal year closing & opening balances carry forward
- [ ] P0 Reports [REPORT]: day book, cash book, bank book, ledger, trial balance, P&L, balance sheet, receivable/payable ageing, VAT registers
- [ ] P0 Bank reconciliation (statement import CSV/XLSX, auto-match, manual match)
- [ ] P1 Export to Tally (XML) / generic accounting CSV
- [ ] P1 Expense management with attachments & approval

**Phase 4 exit criteria:** end-to-end purchase → stock → sale → return → payment → GL balanced for a generic item, with FEFO, schemes, loose units, shift close, all imports/exports working; property tests green.

---

# PHASE 5 — Pharmacy Retail MVP (module `pharmacy`)

## M5.1 Medicine master (pharmacy extension of Item)
- [ ] P0 `MedicineProfile`: generic name (INN), salt composition (multi-API with strength & unit), dosage form, strength, route, therapeutic class (ATC code optional), **drug schedule** (Samuha KA/KHA/GA via rules engine), special flags (e.g., Pregabalin Rx-mandatory, Dicyclomine/Promethazine record-keeping — CR-DDA-03), DDA registration number, marketing authorization holder, pregnancy/lactation category, controlled-drug storage required, cold-chain required, pack description, max dispensable qty without Rx (setting)
- [ ] P0 Generic ↔ brand mapping; substitute finder by identical salt+strength+form; price comparison
- [ ] P0 Medicine search: brand, generic, salt, barcode, manufacturer; typo-tolerant trigram; Devanagari & romanized; results show stock, nearest expiry, MRP, schedule badge; < 1 s p95 on 100k items
- [ ] P0 Medicine import template (all fields) + global catalogue link/copy; bulk schedule assignment with audit
- [ ] P0 Medicine export incl. schedule & salt columns; DDA-format product list export
- [ ] P1 Drug interaction database integration (licensed source or curated) — dependency for M13/M14
- [ ] P1 Dosage label templates (morning/afternoon/night pictograms, Nepali instructions)

## M5.2 Drug rules engine (Samuha enforcement)
- [ ] P0 Rule set model (versioned, effective date, published via Control Plane M3.10)
- [ ] P0 Rule actions at billing time: `REQUIRE_PRESCRIPTION`, `REQUIRE_PRESCRIBER_REGISTRATION`, `REQUIRE_PATIENT_IDENTITY`, `REQUIRE_REGISTER_ENTRY`, `REQUIRE_PHARMACIST_ROLE`, `MAX_QTY`, `WARN`, `BLOCK`
- [ ] P0 Enforcement both client-side (UX) and server-side (authoritative); offline enforcement using cached rule set
- [ ] P0 Override policy (which rules can be overridden, by which role, with reason; KA never overridable)
- [ ] P0 Compliance log of every rule evaluation outcome per sale line

## M5.3 Prescriptions
- [ ] P0 `Prescription`: patient, prescriber, date (BS/AD), source (paper scan/photo, e-Rx, verbal-not-allowed flag), validity, diagnosis (optional), items (medicine/generic, dose, frequency, duration, qty), attachments (multi-page photo), refills allowed/used, status
- [ ] P0 Capture UX at POS: camera/scan, quick prescriber search/add, link Rx lines to bill lines, reuse existing valid Rx for refills
- [ ] P0 Prescription validity checks & expired Rx flag
- [ ] P0 Prescription log register & search (by patient/doctor/drug/date) — [REPORT] + export
- [ ] P1 OCR assist for drug names from photo (suggestions only, pharmacist confirms)

## M5.4 POS / counter billing
- [ ] P0 Layout optimized for 1366×768 and touch; keyboard-first: F2 search, F3 customer, F4 prescription, F8 payment, F9 hold, F10 save+print, Ctrl+R returns, Esc clear; scanner input auto-detect
- [ ] P0 Add item → FEFO batch auto-selected (override shows batch picker with expiry & qty, needs permission + reason) → qty in strip/tablet/box → discount → tax
- [ ] P0 Inline alerts: schedule badge & required actions, near-expiry batch warning, low stock, substitute suggestions when out of stock ("add to shortbook" / "create promise order")
- [ ] P0 Customer quick search/add (phone first), patient selection, doctor selection
- [ ] P0 Payment modal: split tender, QR display for Fonepay/eSewa/Khalti, change due, credit sale checks
- [ ] P0 Print receipt (58/80mm thermal, A5/A4), reprint marked copy, WhatsApp/SMS digital bill
- [ ] P0 Billing performance: add item < 300 ms, complete bill < 5 s total for 5 items; no full-page reloads
- [ ] P0 Hold/resume bills, multiple tabs, draft recovery after browser crash
- [ ] P0 Returns from POS (search original invoice by number/phone/date)
- [ ] P0 Cash drawer kick on cash payment (desktop agent)
- [ ] P1 Customer-facing display (second screen) showing items & total & QR
- [ ] P1 Quick keys / favourites grid for common OTC items

## M5.5 Digital narcotic & controlled drug register
- [ ] P0 Register auto-entry on posting sale of KA (and configured KHA/special) items: date, patient name/address/ID, prescriber name & reg no, drug, batch, qty, running balance, dispensing pharmacist (credential-verified), Rx attachment link, signature capture (touch/pen pad optional)
- [ ] P0 Receipts into register from GRN (supplier, invoice, batch, qty) & adjustments (with witness)
- [ ] P0 Running balance per drug/batch per branch; server recomputation & discrepancy alert
- [ ] P0 Locked storage location enforced for KA items (location type = locked cabinet)
- [ ] P0 Narcotic stock reconciliation session (physical vs register) with witness, variance reason, approval
- [ ] P0 Register views in DDA format; print per drug per period; export PDF/XLSX; one-click inspection export
- [ ] P0 Register entries immutable; corrections via annotated correction entry
- [ ] P1 Monthly/quarterly narcotic consumption report for authorities (CR-DDA-13)

## M5.6 Pharmacy purchasing specifics
- [ ] P0 GRN validations: schedule-specific (KA supplier licence check), cold-chain items require temperature on receipt, short-expiry acceptance approval
- [ ] P0 Expiry/breakage claim to supplier workflow & tracking
- [ ] P0 Reorder suggestions: 30-day moving average × lead time + safety stock; editable; convert to PO
- [ ] P1 Distributor price comparison (manual price lists import) pre ERP-to-ERP

## M5.7 Patient medication history & counseling (MVP depth)
- [ ] P0 Patient purchase/medication history at POS (last 10 dispensations, chronic meds)
- [ ] P0 Counseling note quick capture (dose, side effects, interactions, storage) with templates; linked to sale
- [ ] P0 Allergy flag display & warning on matching salt
- [ ] P1 Duplicate therapy warning (same salt within active duration)

## M5.8 Pharmacy dashboards & reports
- [ ] P0 Branch dashboard: today sales, bills, avg bill value, payment mode split, top items, low stock, near-expiry value, unsynced docs, pending Rx captures, compliance alerts
- [ ] P0 Reports [REPORT]: daily sales summary (with VAT), sales register, item-wise sales, doctor-wise sales, schedule-wise sales (KA/KHA/GA), margin by item/category/manufacturer, expiry loss, returns analysis, discount given, user-wise sales & voids, shift reports, prescription log, substitute sales, shortbook
- [ ] P1 Owner mobile-responsive dashboard (PWA)

## M5.9 Pharmacy settings
- [ ] P0 [SETTING] items: FEFO strict/soft, near-expiry thresholds, allow loose sale default, max discount by role, rounding, Rx required behaviour for KHA (block vs warn if CR allows), print format defaults, customer mandatory above amount, credit sale allowed, negative stock policy, invoice language
- [ ] P0 Branch profile: DDA licence no/expiry, pharmacist-in-charge, opening hours, printer profiles

## M5.10 Onboarding & data migration tooling
- [ ] P0 Tenant onboarding wizard (in-app): business profile → legal entity (PAN/VAT) → branch & DDA licence → users & roles → printers → import medicines → import opening stock (batch/expiry/qty/rate/MRP) → import customers & balances → import suppliers & balances → settings review → test bill → go-live checklist
- [ ] P0 Opening stock import with validation (expired batches flagged, negative qty rejected, unknown items create-or-map)
- [ ] P0 Opening balances (party receivable/payable) import
- [ ] P0 Parallel-run support: "training mode" branch flag (documents watermarked TRAINING, not synced to CBMS, excluded from reports) with reset
- [ ] P1 Importers for top legacy systems from M0.2

**Phase 5 exit criteria:** internal pilot pharmacy (online) runs a full day: purchase with schemes & batches, 200+ bills with KA/KHA/GA enforcement, returns, narcotic register, shift close, reports — zero stock/GL discrepancies.

---

# PHASE 6 — Offline POS & Desktop

## M6.1 Offline data layer (web)
- [ ] P0 Dexie schema for items, batches, stock snapshot, prices, tax & drug rule sets, customers, patients (recent/limited), doctors, settings, number ranges, outbox, attachments queue
- [ ] P0 Initial snapshot download with progress; delta sync by `server_seq` cursor; background refresh every N minutes when online
- [ ] P0 Storage persistence request; quota monitoring; data encryption at rest in browser (WebCrypto key derived from device credential)
- [ ] P0 Service worker caches app shell & POS routes; app boots offline

## M6.2 Sync engine
- [ ] P0 Outbox with ordered push, idempotency, per-document result handling, exponential backoff, manual "sync now"
- [ ] P0 Server sync endpoints (pull deltas, push batch, ack), conflict rules from ARCHITECTURE §7.3, discrepancy tasks
- [ ] P0 Number range leasing, low-range warning, FY rollover guard
- [ ] P0 Sync status UI: online/offline indicator, pending count, last successful sync, error list with resolution guidance
- [ ] P0 Attachment upload queue (prescription photos) with retry
- [ ] P0 Chaos tests: kill network mid-push, duplicate push, clock skew (device time wrong — detect & block beyond tolerance), two offline devices selling last unit, FY boundary offline
- [ ] P1 Multi-device LAN sync (branch-local hub) — evaluate need from pilot

## M6.3 Desktop app (Tauri)
- [ ] P0 Tauri shell wrapping POS web app; auto-start; kiosk-ish window mode
- [ ] P0 Local durable store (SQLite) mirroring IndexedDB for robustness against browser cache clearing
- [ ] P0 Hardware bridge: ESC/POS thermal printing (USB/Serial/Network), cash drawer kick, raw printer selection, barcode scanner (HID) handling, customer display, weighing scale (P2)
- [ ] P0 Signed installers (Windows MSI/EXE first), auto-update with channel & staged rollout (Control Plane M3.10)
- [ ] P0 Minimum spec test on Windows 10, 4 GB RAM
- [ ] P1 Local backup export (encrypted) of unsynced data to USB

## M6.4 Offline compliance
- [ ] P0 Drug rules enforced offline from cached rule set with version shown; rule set expiry (force refresh after N days)
- [ ] P0 Narcotic register entries created offline & reconciled on sync
- [ ] P0 Offline invoices printed with valid numbers & queued for CBMS (per CR-IRD-06)

**Phase 6 exit criteria:** 72-hour offline soak test on 2 devices at one branch, 1,000 bills, reconnect → 100% synced, zero duplicate numbers, register balances correct.

---

# PHASE 7 — IRD e-Billing, CBMS & Payments

## M7.1 IRD e-billing conformance
- [ ] P0 Implement every requirement from CR-IRD-04 checklist (immutability, cancel via credit note, reprint counter "Copy of Original", audit log, user log, materialized view/sales register format, backup)
- [ ] P0 Invoice templates validated against CR-IRD-05 fields (en & ne)
- [ ] P0 Amount in words (Nepali & English) test suite with edge values
- [ ] P0 IRD-format exports: sales book, purchase book, materialized view report, audit trail report
- [ ] P0 Prepare & submit IRD software approval documentation; track audit feedback items here

## M7.2 CBMS integration
- [ ] P0 [INTEGRATION] CBMS adapter per CR-IRD-07: bill post, return post, auth, sandbox
- [ ] P0 Per-document sync status (pending/synced/failed/not-required) visible on invoice & list filters
- [ ] P0 Queue on `critical` Celery queue; retry policy; daily reconciliation report (local vs CBMS acknowledgements)
- [ ] P0 Tenant setting: CBMS enabled, credentials per legal entity, threshold-based guidance
- [ ] P0 Platform console: CBMS health across tenants

## M7.3 Payment gateways
- [ ] P0 [INTEGRATION] eSewa (ePay v2), Khalti (ePayment), Fonepay dynamic QR, ConnectIPS — per tenant merchant credentials (per CR-PAY-01)
- [ ] P0 POS QR flow with polling/webhook confirmation, timeout, cancel, fallback to manual reference
- [ ] P0 Payment link on digital invoice ("PAY NOW") for credit customers
- [ ] P0 Settlement reconciliation report per gateway

## M7.4 Messaging providers
- [ ] P0 [INTEGRATION] SMS gateway (chosen in Phase 0), delivery reports, sender ID, credit metering
- [ ] P0 [INTEGRATION] WhatsApp Business Cloud API: template management & approval status, opt-in records, media (PDF invoice), webhook for replies → ticket/notes
- [ ] P0 Email provider with SPF/DKIM/DMARC per sending domain

## M7.5 Tenant-facing compliance for tax
- [ ] P0 VAT summary dashboard per legal entity
- [ ] P0 Fiscal year close wizard (check unsynced, lock period, roll numbering, carry balances)

---

# PHASE 8 — Pharmacy Compliance Suite (module `pharmacy_compliance`)

## M8.1 Licences & credentials
- [ ] P0 Licence register: DDA pharmacy licence, PAN/VAT cert, company registration, local government recommendation (CR-DDA-04), pharmacist NPC certificates, fire/municipal permits — document, number, issue/expiry, renewal status
- [ ] P0 Renewal alerts (60/30/15 days + overdue) to owner & pharmacist-in-charge; dashboard widget
- [ ] P0 Block/warn setting when pharmacist-in-charge credential expired

## M8.2 CSDD 2024 self-inspection
- [ ] P0 Indicator library from fixture (16 components, 121 indicators), versioned
- [ ] P0 Auto-evaluated indicators from system data (e.g., narcotic register maintained, FEFO enabled, temperature logs present, counseling records exist, ADR process defined) + manual indicators with evidence upload
- [ ] P0 Self-inspection session: assign inspector, answer/score, evidence, comments, corrective actions (→ tasks with due dates), sign-off
- [ ] P0 Compliance score dashboard by component with trend over time; baseline vs target
- [ ] P0 Monthly self-audit reminder
- [ ] P0 Export inspection report PDF/XLSX

## M8.3 SOPs, quality policy, service strategy, premises
- [ ] P0 Document library (quality policy, SOPs, emergency protocol, opening hours) with versions, approval, staff read-acknowledgement tracking
- [ ] P0 Premises checklist & rack/shelf layout records (Location tree reuse)

## M8.4 Storage conditions & GSDP (retail level)
- [ ] P0 Temperature/humidity log per storage location (manual twice-daily entry with reminders; CSV logger import)
- [ ] P0 Excursion detection → alert → affected batches auto-quarantine (setting) → disposition (release/destroy/return) with approval
- [ ] P0 Cold-chain receipt check at GRN

## M8.5 Pharmacovigilance (ADR)
- [ ] P0 ADR form (patient, suspected drug(s) with batch, reaction, onset, severity, outcome, reporter, concomitant meds) per CR-DDA-07 format
- [ ] P0 ADR register with follow-up status; export in DDA format; submission tracking
- [ ] P1 Batch-level ADR signal view (count of ADRs per batch/manufacturer)

## M8.6 Recalls
- [ ] P0 Recall notice entry (source DDA/manufacturer, reference, items, batches, class, instructions, deadline, attachment)
- [ ] P0 Instant impact: stock by branch/location for affected batches; auto-quarantine; block sale
- [ ] P0 Customer trace: patients/customers who purchased affected batches with contact → notification campaign (SMS/WhatsApp) with delivery tracking
- [ ] P0 Return to supplier/destroy workflow; recall closure report & audit trail
- [ ] P1 Platform-level recall broadcast: console publishes recall once → all tenants' matching batches flagged

## M8.7 Complaints, training & CPD, inspection package
- [ ] P0 Client complaint register (category, description, action, resolution, closure time) [MASTER]+[REPORT]
- [ ] P0 Training records (topic, date, trainer, attendees, attachments) & CPD log per pharmacist with hours
- [ ] P0 **One-click DDA Inspection Package**: select period → generate ZIP (stock register, batch records, expiry report, narcotic register, prescription log, ADR reports, complaints, training, temperature logs, licences, self-inspection) with PDF index, hash manifest & generation audit; target < 2 minutes
- [ ] P0 DDA Inspector role temporary access (read-only compliance screens, time-boxed, audited)

---

# PHASE 9 — Pilot, Hardening & Commercial Launch

## M9.1 Pilot
- [ ] P0 3–5 pilot pharmacies (mix: urban online, semi-urban unreliable internet, small chain)
- [ ] P0 Onboarding via console playbook; parallel run 1 week; go-live sign-off form
- [ ] P0 Daily pilot stand-up; issue triage SLA; weekly pilot report (bugs, UX friction, performance, sync incidents)
- [ ] P0 Measure BRD baselines: billing time/item, CSDD score, expiry losses, inspection prep time

## M9.2 Hardening
- [ ] P0 Performance test (Track X-PERF) passed at 10× pilot load
- [ ] P0 Security: external penetration test; fix all high/critical; ASVS L2 checklist
- [ ] P0 DR drill: restore production to new environment within RTO; verify RPO
- [ ] P0 Accessibility audit of POS & key flows
- [ ] P0 Translation review by native Nepali pharmacist

## M9.3 Support readiness
- [ ] P0 Knowledge base: 50+ articles (en/ne) + short videos for top tasks
- [ ] P0 Support rota & escalation matrix; hardware troubleshooting guides (printer drivers, scanner modes)
- [ ] P0 Status page live

## M9.4 Legal & commercial
- [ ] P0 ToS, Privacy Policy, DPA, SLA published via console; acceptance flow live
- [ ] P0 Pricing live; payment collection live; invoice our first customers
- [ ] P0 IRD software approval status resolved (or launch limited to below-threshold customers with clear messaging)
- [ ] P1 Reseller/implementation partner agreements (district-level partners)

## M9.5 Launch
- [ ] P0 Marketing website with pricing, demo booking → CRM
- [ ] P0 Launch checklist sign-off (product, eng, support, compliance, finance)
- [ ] P0 Post-launch 30-day hypercare plan

---

# PHASE 10 — Patient Engagement

## M10.1 Promise orders
- [ ] P0 Create from POS when out of stock: patient, items, qty, advance payment (optional), expected date
- [ ] P0 Reservation on GRN (priority allocation), auto notify patient (SMS/WhatsApp), pickup → convert to invoice
- [ ] P0 Ageing report & overdue flags; cancel with refund

## M10.2 Refill reminders & chronic care
- [ ] P0 Chronic condition tagging (diabetes, hypertension, thyroid, asthma, epilepsy, etc.) & regimens
- [ ] P0 Refill schedule computed from qty ÷ daily dose; reminder N days before run-out; template en/ne; opt-in/out; quiet hours
- [ ] P0 Refill conversion tracking (reminder → purchase within X days) & dashboard
- [ ] P1 Adherence score per patient

## M10.3 Loyalty & family ledger
- [ ] P0 Points rules (earn per NPR, exclusions e.g., KA drugs, redemption rate, expiry), tiers (P1)
- [ ] P0 Redeem at POS as payment mode; statement; cross-branch within tenant
- [ ] P0 Family ledger: household purchases & credit combined statement

## M10.4 Counseling & follow-up (full)
- [ ] P0 Structured counseling record templates by therapeutic class; patient acknowledgement
- [ ] P0 Follow-up & referral tracking (refer to doctor/hospital with reason), outcomes

## M10.5 Communication centre
- [ ] P0 Campaigns (health tips, vaccination drives) with consent filtering, credit estimate, schedule, delivery analytics
- [ ] P0 Two-way WhatsApp inbox (P1) linked to patient

---

# PHASE 11 — Pharmacy Chains (multi-branch)

## M11.1 Central masters & price control
- [ ] P0 HQ-controlled item master, price lists, schemes; branch-level override permissions (setting)
- [ ] P0 Price push with effective date across branches; offline devices pick up on sync

## M11.2 Central purchasing & distribution
- [ ] P0 Branch indent → HQ consolidation → consolidated PO → warehouse GRN → branch transfers
- [ ] P0 Auto-replenishment from warehouse based on branch min/max
- [ ] P0 Inter-branch transfer suggestions for slow/near-expiry stock

## M11.3 Chain reporting & control
- [ ] P0 Consolidated dashboards (sales, stock value, expiry exposure, compliance score per branch), branch comparison
- [ ] P0 Consolidated VAT per legal entity; inter-branch accounting (branch accounts)
- [ ] P0 Central customer & loyalty

## M11.4 Chain compliance
- [ ] P0 Centralized recall execution & status per branch
- [ ] P0 Compliance leaderboard & corrective action tracking across branches

---

# PHASE 12 — Wholesale / Distributor (module `wholesale`) & ERP-to-ERP (module `b2b_connect`)

## M12.1 B2B sales
- [ ] P0 B2B tax invoices with retailer PAN, schemes, trade discounts, cash discount on prompt payment
- [ ] P0 Retailer licence validation (DDA licence no/expiry stored on party; block KA/KHA sales to unlicensed)
- [ ] P0 Order booking by sales reps (mobile PWA), order → pick → pack → invoice → dispatch
- [ ] P0 Credit control: limits, overdue block, collection by reps with receipt, ageing, auto reminders

## M12.2 Warehouse operations (lite)
- [ ] P0 Multi-warehouse, bins, pick lists (FEFO), packing slips, dispatch/e-way docs as applicable
- [ ] P1 Handheld scanning flows

## M12.3 Delivery & POD
- [ ] P0 Route planning (manual grouping by area P0; optimization P1), delivery run sheets, driver app PWA, POD (signature/photo/OTP), returns on delivery

## M12.4 Territory & rep performance
- [ ] P0 Territories, beats, rep targets, visit logs with geo, performance reports

## M12.5 GSDP (distribution)
- [ ] P0 Temperature zone storage, humidity logs, vehicle temperature records, excursion quarantine, GSDP self-inspection checklist (CR-DDA-11)

## M12.6 ERP-to-ERP ordering network
- [ ] P0 Distributor publishes catalogue, stock availability (banded or exact, setting), prices & schemes to connected retailers (both on platform = native link)
- [ ] P0 Retailer ↔ distributor connection request/approval; party mapping; item mapping (auto by barcode/DDA reg no; manual memory)
- [ ] P0 Retailer creates PO in NPMS → appears as sales order at distributor → invoice → **auto-GRN draft at retailer with batches/expiries** → retailer confirms receipt
- [ ] P0 Multi-distributor price & availability comparison for a shortbook
- [ ] P0 Off-platform distributors: [INTEGRATION] EDI/REST/CSV adapters
- [ ] P1 B2B self-service ordering portal for retailers not on platform

---

# PHASE 13 — Hospital Pharmacy (module `hospital_pharmacy`)

- [ ] **M13.1** P0 HMS/EMR integration: [INTEGRATION] HL7 v2 (ORM/RDE/ADT) and FHIR R4 (MedicationRequest, MedicationDispense, Patient, Encounter); e-prescription queue (OPD); standalone mode if no HMS
- [ ] **M13.2** P0 Formulary management (approved list, restricted drugs needing approval, generic substitution policy), P0 drug-drug interaction & allergy checks (licensed DB)
- [ ] **M13.3** P0 IPD: ward indents, ward stock issue, per-patient dispensing, returns from ward, P1 missed-dose alerts & MAR integration, P0 charges auto-post to patient running bill, P0 discharge medication reconciliation
- [ ] **M13.4** P0 OT/ICU/Emergency: narcotic issue with expected vs actual use, wastage documentation with witness, crash-cart kits (kit templates, replenishment), P0 monthly ward stock reconciliation
- [ ] **M13.5** P0 Insurance (SSF/HIB) claim line generation (CR-INS-01), package billing hooks, P1 home medication tracking

---

# PHASE 14 — Analytics & AI Intelligence (module `intelligence`)

- [ ] **M14.1** P0 Analytics store (separate schema/ClickHouse), nightly & near-real-time ETL, semantic metrics layer, tenant-scoped BI dashboards (custom dashboard builder P1)
- [ ] **M14.2** P0 Demand forecasting (seasonality incl. Nepal festivals/monsoon disease seasons), P0 dynamic reorder levels, P0 forecast accuracy tracking (MAPE) per item, P1 auto-PO drafts
- [ ] **M14.3** P0 Dead-stock & expiry-risk prediction with recommended action (transfer/return/push sale), P1 substitute demand mapping
- [ ] **M14.4** P1 Customer intelligence: chronic cohorts, churn risk, refill timing personalization, basket recommendations (never for Rx drugs)
- [ ] **M14.5** P1 Clinical & compliance intelligence: antibiotic dispensing pattern alerts, anomaly detection (after-hours KA sales, excessive discounts/voids), ADR batch signals
- [ ] Cross: model registry, versioned models per tenant cohort, explainability text in UI, opt-out, no PHI leaves tenant boundary for training without consent

---

# PHASE 15 — Omnichannel, Patient Portal & Mobile Apps

- [ ] **M15.1** P0 Patient portal/PWA (`apps/portal`): tenant-branded storefront, medicine search (OTC browse; Rx items require prescription upload), cart, prescription upload, order tracking, reorder, reminders, invoices, loyalty
- [ ] **M15.2** P0 Order management at pharmacy: online order queue, pharmacist Rx verification, substitute approval by patient, packing, payment (gateway/COD), click-and-collect
- [ ] **M15.3** P0 Delivery: own riders app or partner integration (Pathao etc. — verify APIs), live tracking, POD, cold-chain items delivery restrictions
- [ ] **M15.4** P0 Owner mobile app (Expo): sales, stock alerts, approvals (discount/override/PO), compliance alerts, push notifications
- [ ] **M15.5** P1 Telepharmacy: secure chat/video consult with pharmacist, consult notes stored as counseling records; P1 Digital health ID/MoHP e-health integration when available; FHIR patient medication record exchange with consent

---

# PHASE 16 — Future Verticals (roadmap skeletons; reuse Kernel + Core)

> Each vertical starts with its own M16.x.0 **Discovery & compliance** milestone and must reuse: Patients (MPI), Practitioners, Catalogue, Inventory, Sales, Payments, Accounting, Documents, Notifications, Import/Export/Print.

### M16.1 Warehouse Management System (`warehouse`)
- [ ] Inbound: ASN, dock scheduling, receiving, QC hold, putaway rules
- [ ] Storage: zones/aisles/racks/bins, capacity, slotting, temperature zones
- [ ] Outbound: wave/batch/zone picking, pick-to-light ready, packing, cartonization, shipping labels
- [ ] Cycle counting, replenishment, cross-docking, returns processing (reverse logistics)
- [ ] Handheld RF/Android scanner app; labour productivity; yard management (P2)

### M16.2 Clinic / OPD (`clinic`)
- [ ] Appointments & queue (token), practitioner schedules, online booking
- [ ] Encounter/EMR: vitals, chief complaint, history, diagnosis (ICD-10/11), e-prescription → pharmacy module, lab orders → lab module, referrals
- [ ] Clinic billing (services, packages), follow-ups, certificates (medical/sick leave)
- [ ] Practitioner revenue sharing

### M16.3 Dental (`dental`)
- [ ] Dental chart (FDI numbering), per-tooth conditions & procedures, treatment plans with staged estimates
- [ ] Procedure catalogue & materials consumption from inventory; lab work (crowns/dentures) tracking with external labs
- [ ] Imaging attachments (X-ray/OPG), consent forms with signature, recall reminders (6-month check-ups)
- [ ] NDC registration for dentists

### M16.4 Laboratory (`lab`)
- [ ] Test catalogue, panels, sample collection & barcoding, worklists, analyzer interfacing (ASTM/HL7), result entry & validation, reference ranges, report printing/sharing, QC (Levey-Jennings)

### M16.5 Hospital (HMS) (`hospital`)
- [ ] Registration/ADT, bed management, OPD/IPD/Emergency, nursing, OT scheduling, billing & packages, insurance/SSF, discharge summary, MRD, radiology (PACS link), dietary, CSSD, HR/payroll (optional)

---

# CROSS-CUTTING TRACKS (continuous)

## X-SEC — Security & Privacy
- [ ] P0 Threat model (STRIDE) for kernel, POS/offline, control plane impersonation, integrations — refreshed each phase
- [ ] P0 OWASP ASVS L2 checklist tracked; secure headers (CSP, HSTS, frame-ancestors), CSRF, CORS allow-list
- [ ] P0 Dependency, container, IaC scanning in CI; SBOM per release
- [ ] P0 Field-level encryption for sensitive PII; key rotation procedure — **blocking for `identity.TwoFactorDevice.secret`, which is currently stored in clear text: anyone with read access to that table can mint valid second-factor codes**
- [ ] P0 Secrets rotation schedule (DB, gateway keys, JWT signing keys)
- [ ] P0 Least-privilege production access; break-glass procedure with audit; quarterly access review
- [ ] P0 Privacy: consent management, data subject access/export/correction, data minimization, retention schedules (CR-PRIV-01)
- [ ] P0 Incident response plan & breach notification templates; tabletop exercise twice a year
- [ ] P1 Bug bounty / responsible disclosure (`SECURITY.md`)
- [ ] P1 Annual external pentest

## X-QA — Quality
- [ ] P0 Test pyramid targets; critical domain tests (tax, numbering, stock, narcotic, sync, entitlements, tenancy) ≥ 90% branch coverage
- [ ] P0 Playwright e2e suites per module; runs nightly on staging & on release candidates
- [ ] P0 Regulatory regression pack (invoice fields, register formats, rule sets) — must pass before any release
- [ ] P0 Test data management: factories, anonymized fixtures, no production PII in non-prod
- [ ] P1 **`transactional_db` tests will fail until addressed**: Django flushes with `TRUNCATE`, and the audit table's append-only trigger refuses it (by design). When a test genuinely needs a real transaction, add a fixture that drops and restores that one trigger around it — do not weaken the trigger itself
- [ ] P1 Contract tests for integrations; mutation testing on tax/numbering modules
- [ ] P1 Manual exploratory test charters per release; UAT sign-off template for pilot customers

## X-PERF — Performance & Scalability targets
- [ ] P0 API p95 < 300 ms (reads), < 800 ms (document post); medicine search p95 < 1 s @ 1M SKUs across tenant
- [ ] P0 POS add item < 300 ms; bill completion < 5 s; offline boot < 3 s
- [ ] P0 CBMS sync enqueue < 1 s; push p95 < 3 s (external dependency tracked)
- [ ] P0 Scale test: 5,000 tenants, 20,000 branches, 2M bills/day aggregate, 100M stock ledger rows
- [ ] P0 DB: indexes reviewed per query plan, partitioning live for ledgers, autovacuum tuned, slow query log alerts
- [ ] P1 Load test scripts (k6/Locust) versioned in `deployment/loadtest/`; run per release

## X-OPS — Reliability, Backup & DR
- [ ] P0 SLOs: availability 99.5% (cloud app), error budget policy
- [ ] P0 RPO ≤ 15 min (WAL archiving), RTO ≤ 4 h; quarterly restore drill with report
- [ ] P0 Backups: DB (pgBackRest), object storage replication, config/secrets backup; encrypted; geo-separate copy; 7 daily / 4 weekly / 12 monthly retention (+ statutory archives)
- [ ] P0 Per-tenant point-in-time data recovery procedure (restore to side DB, extract tenant rows, audited merge)
- [ ] P0 Runbooks: deploy, rollback, DB failover, Redis failure, queue backlog, CBMS outage, payment gateway outage, SMS outage, disk full, certificate expiry, compromised credential
- [ ] P0 On-call rotation & alert tuning (no alert without runbook link)
- [ ] P1 Chaos days quarterly

## X-DOCS — Documentation
- [ ] P0 `docs/adr/` maintained; architecture diagrams (C4: context, container, component) updated per phase
- [ ] P0 API reference auto-published; integration guides for partners (distributors, HMS)
- [ ] P0 User guides per module (en/ne), in-app contextual help links
- [ ] P0 Admin guide (tenant owners): roles, settings, imports, compliance
- [ ] P0 Operations guide (on-prem installation, upgrade, backup)
- [ ] P0 Release notes per version (customer-facing) & internal changelog

## X-SUP — Customer success operations
- [ ] P0 Onboarding playbooks by segment; training curricula (counter staff < 2 h, pharmacist < 1 day) with certificates
- [ ] P0 AMC renewal process & reminders
- [ ] P1 NPS surveys; customer advisory group of pharmacists

## X-LEGAL — Legal & Governance
- [ ] P0 Company registration, PAN/VAT for platform business; software copyright registration
- [ ] P0 Customer agreement (licence + AMC and SaaS variants), DPA, SLA, reseller agreement templates
- [ ] P0 Third-party licence compliance (OSS licences inventory; drug database licensing)
- [ ] P1 Cyber insurance evaluation

## X-GTM — Go-to-market
- [ ] P0 Positioning, website, demo tenant, sales deck, ROI calculator (expiry savings, time saved)
- [ ] P0 Channel strategy: direct (valley), partners (districts), associations (NCDA / pharmacy associations — verify names), distributor-led adoption via ERP-to-ERP
- [ ] P1 Case studies from pilots; webinars in Nepali

---

# Appendix A — Module Catalogue (codes)

| Code | Name | Layer | Depends on | Phase |
|------|------|-------|------------|-------|
| `kernel.*` | Tenancy, identity, RBAC, audit, registry, entitlements, settings, files, notifications, jobs, import/export/print | Kernel | — | 2 |
| `control.*` | Console, tenants, plans, billing, accounting, CRM, tasks, helpdesk, policies, releases, analytics | Control | kernel | 3 |
| `core.org` | Legal entities, branches, locations, devices | Core | kernel | 2/4 |
| `core.parties` | Customers, suppliers, contacts | Core | core.org | 4 |
| `core.patients` | MPI, families, consents | Core | core.org | 4 |
| `core.practitioners` | Doctors, dentists, pharmacists, credentials | Core | core.org | 4 |
| `core.catalog` | Items, units, barcodes, manufacturers, brands, categories | Core | core.org | 4 |
| `core.pricing` | Price lists, discounts, schemes | Core | core.catalog | 4 |
| `core.inventory` | Batches, ledger, balances, adjustments, transfers, counts | Core | core.catalog | 4 |
| `core.purchasing` | Requisitions, POs, GRNs, returns, shortbook | Core | core.inventory, core.parties | 4 |
| `core.sales` | Invoices, returns, shifts, quotations | Core | core.inventory, core.parties | 4 |
| `core.tax` | Tax categories, rates, registers | Core | core.org | 4 |
| `core.payments` | Modes, gateway intents, receipts, cheques | Core | core.sales | 4 |
| `core.accounting` | CoA, journals, posting rules, periods, statements | Core | core.org | 4 |
| `pharmacy` | Medicine profile, drug rules, prescriptions, POS, narcotic register | Module | core.* | 5 |
| `pharmacy_offline` | Offline POS & desktop sync (feature of pharmacy/sales) | Module | pharmacy | 6 |
| `ird_ebilling` | IRD conformance, CBMS | Module | core.sales, core.tax | 7 |
| `pharmacy_compliance` | Licences, CSDD, SOPs, GSDP logs, ADR, recalls, complaints, training, inspection package | Module | pharmacy | 8 |
| `engagement` | Promise orders, reminders, loyalty, counseling, campaigns | Module | core.patients, core.sales | 10 |
| `chain` | Central masters, indent consolidation, chain reports | Module | core.* | 11 |
| `wholesale` | B2B sales, credit control, delivery, territories, GSDP distribution | Module | core.* | 12 |
| `b2b_connect` | ERP-to-ERP ordering network | Module | wholesale or pharmacy | 12 |
| `hospital_pharmacy` | HMS integration, formulary, IPD/OT/ICU dispensing | Module | pharmacy | 13 |
| `intelligence` | Analytics store, forecasting, predictions | Module | core.* | 14 |
| `omnichannel` | Patient portal, online orders, delivery | Module | pharmacy, engagement | 15 |
| `telepharmacy` | Chat/video consult | Module | omnichannel | 15 |
| `cold_chain_iot` | Logger/IoT integration | Module | pharmacy_compliance | 8/12 |
| `warehouse` | Full WMS | Module | core.inventory | 16 |
| `clinic` | OPD, appointments, EMR | Module | core.patients | 16 |
| `dental` | Dental charting & treatment plans | Module | clinic | 16 |
| `lab` | Laboratory information system | Module | core.patients | 16 |
| `hospital` | HMS | Module | clinic, lab, pharmacy | 16 |

# Appendix B — Gaps found in BRD v2.0 (now covered above)

| Gap | Covered in |
|-----|-----------|
| Medicines likely VAT-exempt — BRD assumes 13% on all | CR-IRD-01, M4.8 |
| IRD e-billing software **approval** process & feature requirements (no delete, reprint counter, materialized view) | CR-IRD-04, M7.1 |
| Offline invoice numbering legality | CR-IRD-06, ADR-0004, M6.2 |
| Loose/strip sales, pack unit conversions | M4.3, M5.4 |
| Bonus/free quantity schemes (very common in Nepal) | M4.4, M4.6 |
| MRP enforcement & DDA margin caps | M4.4, CR-DDA-09 |
| Cashier shift, denomination count, day-end | M4.7 |
| Sales returns / credit notes & purchase returns / expiry claims | M4.6, M4.7 |
| Physical stock count workflow | M4.5 |
| Accounting (GL, periods, FY close, bank reconciliation) | M4.10, M7.5 |
| BS calendar, fiscal year Shrawan–Ashadh, lakh/crore formatting, amount in words (ne) | M1.2, M2.6 |
| Nepal address master (province/district/local level/ward) | M2.1 |
| Import/export/print framework for every entity | §0.1, M2.8 |
| Opening stock/balance migration & training mode parallel run | M5.10 |
| Subscription lapse → read-only, never lose regulatory records | ARCH §5.3, M2.5 |
| Platform owner console (CRM, help desk, billing, releases, flags, policies) | Phase 3 |
| Support impersonation with consent & audit | M3.2 |
| Rule sets (drug schedules/tax) as versioned data deployments | M3.10, M5.2 |
| Device registry, shared-terminal PIN switch, supervisor override | M2.2 |
| Professional credential gating (pharmacist-only actions) | M2.3 |
| Tamper-evident audit | M2.4 |
| Data residency, privacy act, consent | CR-PRIV-*, X-SEC |
| DR targets (RPO/RTO), restore drills, per-tenant recovery | X-OPS |
| Legacy Preeti font data conversion | M2.6 |
| Future verticals reuse plan (warehouse, clinic, dental, lab, HMS) | Phase 16, Appendix A |
