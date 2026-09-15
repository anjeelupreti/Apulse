# Nepal e-Health Platform — NPMS (Pharmacy first)

Multi-tenant, module-based e-health platform for Nepal. The first vertical is **pharmacy** (retail, chain, wholesale, hospital pharmacy). Warehouse, clinic, dental, lab, and hospital modules come later and reuse the same kernel and core.

| Folder | Contents |
|--------|----------|
| [backend/](backend/) | Django + DRF API, Celery workers (kernel, core, modules, control plane, integrations) |
| [frontend/](frontend/) | Next.js monorepo with shadcn/ui and Tailwind (tenant web app, owner console, patient portal, desktop POS) |
| [deployment/](deployment/) | Docker, Compose, Kubernetes/Helm, Terraform, Ansible, CI templates, load tests |
| [docs/](docs/) | Architecture, **master checklist**, conventions, control plane design, compliance register, ADRs |

## Start here
1. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
2. [docs/CHECKLIST.md](docs/CHECKLIST.md): the build plan, phase by phase and milestone by milestone
3. [docs/COMPLIANCE_REGISTER.md](docs/COMPLIANCE_REGISTER.md): verify these before coding any regulatory rule
4. [docs/CONVENTIONS.md](docs/CONVENTIONS.md)

## Stack
Python 3.12 · Django 5 · DRF · Celery · Channels · PostgreSQL 16 (RLS) · Redis · S3/MinIO ·
Next.js · TypeScript · shadcn/ui · Tailwind CSS · TanStack Query/Table · Dexie (offline) · Tauri (desktop POS)

## Status
Phase 0 / Phase 1: foundation. No vertical-module code is merged until checklist milestone **M3.4** is closed.
