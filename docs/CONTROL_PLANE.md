# Control Plane — Platform Owner Console Design

> The console is how **we** run the business: sell, provision, bill, support, govern, and ship.
> App: `frontend/apps/console` · API: `/console-api/v1/` · Backend: `backend/control/*`
> Checklist: [CHECKLIST.md — Phase 3](CHECKLIST.md#phase-3--control-plane-platform-owner-console)

---

## 1. Principles

1. **Separate realm.** Platform staff are not tenant users. Separate table, login URL, cookies, 2FA mandatory, IP allow-list.
2. **Least privilege.** Staff roles see only what their job needs; tenant business data (sales, patients) is **not** browsable — only aggregates and support-sanctioned access.
3. **Everything audited.** Every write, every PII read, every impersonation, every export.
4. **Dual control** for dangerous actions: tenant purge, tax/narcotic rule-set publish, write-mode impersonation, data-fix scripts, plan price changes affecting existing tenants.
5. **Console drives configuration, not code.** Plans, features, flags, rule sets, policies, templates, announcements are data.

---

## 2. Information Architecture (navigation)

```
Console
├── Home (KPIs, alerts, my tasks, SLA breaches, system health summary)
├── Sales
│   ├── Leads (list / pipeline board)
│   ├── Activities & Calendar
│   ├── Quotes
│   └── Demo Tenants
├── Customers
│   ├── Tenants
│   ├── Onboarding (projects board)
│   ├── On-Prem Installations & Licences
│   └── Health & Churn Risk
├── Support
│   ├── Tickets (queues)
│   ├── Knowledge Base
│   ├── Canned Responses
│   └── Data Correction Requests
├── Work
│   ├── Tasks (my / team / calendar)
│   └── Playbooks (task templates)
├── Catalogue & Pricing
│   ├── Modules (registry)
│   ├── Features
│   ├── Plans & Versions
│   ├── Add-ons
│   ├── Coupons
│   └── Price Books
├── Billing
│   ├── Subscriptions
│   ├── Invoices & Credit Notes
│   ├── Payments & Reconciliation
│   ├── Dunning
│   └── Usage & Metering
├── Accounting
│   ├── Chart of Accounts
│   ├── Journals
│   ├── Expenses & Payables
│   ├── Bank & Wallets
│   └── Financial Reports (P&L, BS, TB, VAT, Registers)
├── Governance
│   ├── Policies & Acceptances
│   ├── Rule Sets (Drug schedules, Tax, CSDD, Invoice templates)
│   ├── Global Catalogue (reference medicines)
│   ├── Recall Broadcasts
│   └── Announcements & Maintenance Windows
├── Engineering
│   ├── Releases & Changelog
│   ├── Feature Flags & Rollouts
│   ├── Jobs & Dead Letters
│   ├── Integrations Health (CBMS, gateways, SMS, WhatsApp)
│   ├── Sync Health (offline devices)
│   └── System Health
├── Analytics
│   ├── Revenue (MRR/ARR/churn/NRR)
│   ├── Funnel
│   ├── Product Usage & Adoption
│   └── Support Performance
└── Administration
    ├── Staff & Roles
    ├── Teams/Groups & Business Hours
    ├── Console Audit Log
    ├── Notification Templates
    ├── Integrations (our own: SMS, email, WhatsApp, gateways)
    └── Platform Settings
```

---

## 3. Core Data Model (control schema)

```
PlatformStaff ─┬─< StaffRoleAssignment >── StaffRole ──< StaffPermission
               └─< StaffSession / StaffDevice

Lead ──< LeadActivity            Lead ──< Quote ──< QuoteLine
Lead ── (converted_to) ── Tenant

Tenant ──< TenantDomain
Tenant ──< TenantContact
Tenant ──< TenantKycDocument
Tenant ──1 Subscription ──< SubscriptionItem (plan_version | addon, qty)
Tenant ──< TenantModule
Tenant ──< TenantFeatureOverride
Tenant ──< UsageMeter
Tenant ──< OnPremLicence ──< LicenceHeartbeat
Tenant ──< SupportImpersonationSession

Module ──< ModuleVersion ──< Feature
Plan ──< PlanVersion ──< PlanModule
                     └──< PlanFeature (value: bool | limit | quota)
                     └──< PlanPrice (billing_model, cycle, currency, amount, unit)
AddOn ──< AddOnFeature, AddOnPrice
Coupon ──< CouponRedemption

PlatformInvoice ──< PlatformInvoiceLine     PlatformCreditNote
PaymentIntent ──< PaymentAttempt            PlatformPayment ──< PaymentAllocation
DunningRun ──< DunningStep

Account ──< JournalEntry ──< JournalLine    Expense   Vendor   BankAccount ──< BankStatementLine

Ticket ──< TicketMessage (public|internal) ──< Attachment
Ticket ── SlaPolicy ── BusinessHours ── HolidayCalendar
KbArticle ──< KbArticleVersion
CannedResponse
DataCorrectionRequest ──< DataFixExecution (dual approval)

Task ──< TaskChecklistItem, TaskComment, TimeLog     TaskTemplate(Playbook) ──< TaskTemplateItem

PolicyDocument ──< PolicyVersion ──< PolicyAcceptance (tenant user or owner)
Announcement ──< AnnouncementTarget        MaintenanceWindow
RuleSet ──< RuleSetVersion (status, effective_from, approvals, diff)
Release ──< ReleaseNote(en, ne) ──< ReleaseTicketLink
FeatureFlag ──< FlagRule (percentage | allow | deny | cohort | schedule)
ConsoleAuditEvent (append-only, hash-chained)
```

---

## 4. Plans & Entitlements — Initial Matrix (draft, pending M0.3)

| Capability | Starter | Standard | Professional | Enterprise | On-Prem |
|------------|:------:|:--------:|:------------:|:----------:|:-------:|
| Branches included | 1 | 1 | 3 | custom | licence |
| Users included | 3 | 8 | 25 | custom | licence |
| POS devices | 1 | 3 | 10 | custom | licence |
| SKU limit | 5,000 | 25,000 | 100,000 | unlimited | unlimited |
| `pharmacy` (POS, Rx, Samuha rules) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Narcotic register | ✅ | ✅ | ✅ | ✅ | ✅ |
| Offline POS (desktop) | — | ✅ | ✅ | ✅ | ✅ |
| `ird_ebilling` + CBMS | add-on | ✅ | ✅ | ✅ | ✅ |
| `pharmacy_compliance` (CSDD, ADR, recall, inspection pack) | basic (licences, recall) | ✅ | ✅ | ✅ | ✅ |
| `engagement` (reminders, loyalty, promise orders) | — | promise orders | ✅ | ✅ | ✅ |
| `chain` | — | — | ✅ | ✅ | ✅ |
| `wholesale` | — | — | add-on | ✅ | add-on |
| `b2b_connect` | receive only | ✅ | ✅ | ✅ | ✅ |
| `hospital_pharmacy` | — | — | — | ✅ | add-on |
| `intelligence` | — | basic reports | add-on | ✅ | add-on |
| `omnichannel` | — | — | add-on | ✅ | add-on |
| SMS credits / month | 200 | 1,000 | 5,000 | custom | own gateway |
| API & webhooks | — | — | read API | ✅ | ✅ |
| SSO | — | — | — | ✅ | ✅ |
| Support SLA (first response) | 1 business day | 8 business h | 4 business h | 1 h (P1) | per contract |
| Data residency / silo DB | pooled | pooled | pooled | silo option | customer premises |

Billing models supported on every plan: **monthly**, **annual** (discount), **one-time licence + AMC**.

---

## 5. Key Workflows

### 5.1 Lead → Tenant
```
Lead captured → qualified → demo (optional demo tenant auto-provisioned)
→ quote (plan version + add-ons + setup fee, coupon) → e-accept
→ Won → "Convert" pre-fills Provision Wizard
→ KYC docs checklist → provision (idempotent job) → owner invite sent
→ Onboarding playbook tasks created & assigned → invoice issued → payment
→ go-live sign-off → lead closed, tenant active
```

### 5.2 Feature rollout
```
Dev merges behind flag (off) → Release registered (edge)
→ enable for internal tenants → beta cohort (opt-in tenants) at 10% → 50%
→ GA: attach feature to plan versions → remove flag after 2 releases
Kill switch available at every step; every change audited with reason.
```

### 5.3 Rule-set update (e.g., DDA moves a drug to Samuha KHA)
```
Compliance staff drafts RuleSetVersion (edit or XLSX import)
→ validation (unknown items, conflicting rules) → diff vs active
→ effective date set → approval #1 (Compliance lead) → approval #2 (Tech lead)
→ publish → tenants receive event → offline devices refresh on next sync
→ in-app notice "Regulatory update" with plain-language summary (en/ne)
```

### 5.4 Support impersonation
```
Agent opens ticket → "Access tenant" → reason + ticket id
→ check tenant consent setting (always / ask owner / never)
→ read-only session token (30 min) → banner shown in tenant UI
→ need write? → Support Lead approves → write session (15 min)
→ session end → summary appended to ticket → tenant owner notified
```

### 5.5 Subscription lapse
```
Invoice due → reminders → overdue → grace (15 d) with banners
→ read-only (sales/purchases blocked; registers/reports/exports allowed)
→ after N days cancellation → retention window → purge (dual approval, owner notified, export offered)
Manual "payment promise" hold available to Finance (max 7 days, audited).
```

---

## 6. Console Security Checklist

- [ ] Staff login at `console.<domain>` only; not reachable from tenant domains
- [ ] TOTP mandatory; WebAuthn recommended for Super Admin
- [ ] IP allow-list / VPN required for Super Admin, Finance, Developer roles
- [ ] Session 8 h max, 30 min idle
- [ ] PII masking by default in tenant contact views (click-to-reveal is audited)
- [ ] Export of any tenant list requires permission & is audited
- [ ] Dual-approval engine reusable for all dangerous actions
- [ ] Console audit log immutable & hash-chained; weekly review report to Super Admin
- [ ] Break-glass Super Admin account sealed, usage alerts to all founders
