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

## Quick start

```bash
pip install uv                 # once
python tasks.py setup          # install deps, create backend/.env, install git hooks
python tasks.py infra-up       # PostgreSQL, Redis, MinIO, Mailpit in Docker
python tasks.py migrate
python tasks.py dev            # http://127.0.0.1:8000/api/docs/
```

`python tasks.py` lists every task. Details in [CONTRIBUTING.md](CONTRIBUTING.md).

## Stack
Python 3.12 · Django 5 · DRF · Celery · Channels · PostgreSQL 16 (RLS) · Redis · S3/MinIO ·
Next.js · TypeScript · shadcn/ui · Tailwind CSS · TanStack Query/Table · Dexie (offline) · Tauri (desktop POS)

## Status
Phase 1 (foundation). Backend skeleton is running: settings, base models, custom user, DRF error
envelope, health endpoints, Celery queues, enforced layering, CI — all green.
Next: Phase 2 (kernel — tenancy, auth, RBAC, audit, entitlements).

No vertical-module code is merged until checklist milestone **M3.4** is closed.
