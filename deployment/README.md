# Deployment & Infrastructure

## Planned layout

```
deployment/
├── docker/
│   ├── backend.Dockerfile        # multi-stage, non-root, healthcheck (api + worker + beat targets)
│   ├── web.Dockerfile            # Next.js standalone output
│   ├── console.Dockerfile
│   └── nginx/ or caddy/          # reverse proxy, wildcard TLS, security headers
├── compose/
│   ├── docker-compose.dev.yml    # postgres, pgbouncer, redis, minio, mailpit, backend, workers, beat, flower, web, console
│   ├── docker-compose.test.yml   # CI e2e stack
│   └── docker-compose.onprem.yml # on-prem appliance bundle
├── k8s/
│   └── helm/npms/                # charts: api, worker (per queue), beat, channels, web, console, migrations job
├── terraform/
│   ├── modules/                  # network, db, redis, storage, dns, monitoring
│   └── envs/{staging,production}/
├── ansible/                      # VM provisioning, on-prem install/upgrade, hardening
├── observability/
│   ├── grafana/dashboards/       # API, Celery, DB, sync lag, integrations
│   ├── prometheus/rules/         # alerts (each links a runbook)
│   └── loki/
├── backup/
│   ├── pgbackrest/               # full/diff/WAL config
│   └── restore-drill.md
├── ci/                           # reusable GitHub Actions workflow templates (copied to .github/workflows)
├── loadtest/                     # k6 / Locust scenarios (POS burst, sync storm, report load)
└── scripts/                      # bootstrap, seed, rotate-secrets, create-tenant-silo
```

## Environments
| Env | Trigger | Data |
|-----|---------|------|
| local | `make dev` | seeded demo tenants |
| preview | per PR (P1) | ephemeral seed |
| staging | release candidate tag | anonymized, never real PII |
| production | manual approval | Nepal-hosted, backups geo-separated |
| on-prem | signed bundle via update channel | customer premises |

## Targets
99.5% availability · RPO ≤ 15 min · RTO ≤ 4 h · quarterly restore drill. See [docs/CHECKLIST.md](../docs/CHECKLIST.md) M1.4–M1.6 and track X-OPS.
