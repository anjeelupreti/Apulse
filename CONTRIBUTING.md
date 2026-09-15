# Contributing

Read [docs/CONVENTIONS.md](docs/CONVENTIONS.md) before your first change, and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before touching the kernel.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.12.x | `backend/.python-version` pins it |
| uv | latest | `pip install uv` — manages the virtualenv and lockfile |
| Docker Desktop | latest | runs PostgreSQL, Redis, MinIO, Mailpit |
| Node | 22 LTS | frontend (from M1.3) |
| pnpm | 9.x | frontend (from M1.3) |

## First run

```bash
python tasks.py setup       # install deps, create backend/.env, install git hooks
python tasks.py infra-up    # start PostgreSQL, Redis, MinIO, Mailpit
python tasks.py migrate
python tasks.py dev         # http://127.0.0.1:8000
```

`python tasks.py` on its own lists every task.

Local service ports are deliberately non-standard so this stack can run next to other
projects: PostgreSQL **55432**, Redis **56379**, MinIO **59000** (console 59001),
Mailpit SMTP **51025** (UI **51026**).

## Before you push

```bash
python tasks.py lint    # ruff, format, import-linter, mypy, missing-migration check
python tasks.py test
```

CI runs exactly these. `python tasks.py fmt` auto-fixes formatting.

## Rules that block a merge

- **Layering.** `modules → core → kernel → shared`; `shared` imports no framework; modules never
  import each other. Enforced by import-linter, not by convention.
- **Tenant isolation.** Every new tenant-scoped endpoint needs an isolation test.
- **Migrations.** Backward compatible with the previous release (expand → migrate → contract).
- **No user-visible literal strings.** English and Nepali keys both.
- **Regulatory rules.** Do not implement one until its entry in
  [docs/COMPLIANCE_REGISTER.md](docs/COMPLIANCE_REGISTER.md) is verified against a primary source.
- **Definition of Done.** See [docs/CHECKLIST.md](docs/CHECKLIST.md) §0.2.

Two approvals are required for kernel, tenancy, auth, tax, numbering, narcotic register, sync and
billing code. One approval elsewhere.

## Commits and branches

Trunk-based: short-lived branches off `main`, squash merge.
[Conventional Commits](https://www.conventionalcommits.org): `feat(pharmacy): enforce FEFO on sale`.

Do not add co-author or tool-attribution trailers to commits or pull requests.
