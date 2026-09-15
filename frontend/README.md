# Frontend: Next.js Monorepo

pnpm workspaces · Turborepo · Next.js (App Router) · TypeScript strict · shadcn/ui · Tailwind CSS · TanStack Query & Table · react-hook-form + zod · next-intl (en/ne) · Dexie + Serwist (offline) · Tauri (desktop POS)

## Planned layout

```
frontend/
├── package.json  pnpm-workspace.yaml  turbo.json  .nvmrc
├── apps/
│   ├── web/                  # tenant app: pharmacy & all vertical modules (app.<domain>, {tenant}.app.<domain>)
│   │   └── src/app/
│   │       ├── (auth)/       # login, 2fa, reset, invite, tenant select
│   │       ├── (app)/        # shell: sidebar from /me/context nav
│   │       │   ├── dashboard/
│   │       │   ├── pos/            # offline-capable route group
│   │       │   ├── inventory/  purchasing/  sales/  parties/  patients/
│   │       │   ├── pharmacy/  compliance/  engagement/  reports/  accounting/
│   │       │   ├── settings/       # generated from module settings schemas
│   │       │   ├── admin/          # users, roles, branches, devices, audit, billing, integrations
│   │       │   └── jobs/  notifications/  help/
│   │       └── (print)/      # print-only layouts
│   ├── console/              # platform owner console (console.<domain>), separate auth realm
│   ├── portal/               # patient portal / storefront (Phase 15)
│   └── desktop/              # Tauri shell for offline POS + hardware bridge (Phase 6)
│
└── packages/
    ├── ui/                   # shadcn/ui primitives, theme tokens, Devanagari fonts, Storybook
    ├── data-table/           # [MASTER] list contract: filters, saved views, column chooser, bulk, export
    ├── forms/                # RHF + zod helpers, field components, server error mapping
    ├── api-client/           # Orval-generated client + TanStack Query hooks (src/gen/ is generated)
    ├── auth/                 # session handling, <Can>, <Feature>, <ModuleGate>, route guards
    ├── i18n/                 # next-intl setup, formatters (lakh/crore, NPR, BS dates)
    ├── nepali-date/          # BS calendar data, date picker
    ├── offline/              # Dexie schema, sync engine, outbox, number-range leases
    ├── printing/             # print helpers, ESC/POS bridge client
    ├── dataio/               # import wizard (mapping, validation report), export dialog
    ├── shortcuts/            # keyboard shortcut registry & help overlay
    ├── utils/
    ├── config-eslint/  config-typescript/  config-tailwind/
```

## Rules
See [docs/CONVENTIONS.md §5](../docs/CONVENTIONS.md). Data comes only from `@npms/api-client`, tables only from `@npms/data-table`, primitives only from `@npms/ui`, and user-facing text is never a hardcoded literal.

## Status
Skeleton pending. Build order: [docs/CHECKLIST.md](../docs/CHECKLIST.md) M1.3.
