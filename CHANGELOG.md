# Changelog

All notable changes are recorded here. Format: [Keep a Changelog](https://keepachangelog.com);
versioning: [Semantic Versioning](https://semver.org).

## [Unreleased]

### Added
- Planning documents: architecture, master build checklist, engineering conventions, control-plane
  design, compliance register, ADR template.
- Repository root: task runner (`tasks.py`), pre-commit hooks, contributor and security policies,
  issue/PR templates, backend CI workflow.
- Backend skeleton: environment-driven split settings, UUIDv7 base models, custom `identity.User`
  (email *or* phone login), DRF with deny-by-default permissions, bilingual error envelope with a
  registered error-code catalogue, request-id logging, health/readiness/version endpoints, Celery
  queues with request-id propagation, Channels, OpenAPI schema, enforced layering.
- Local development stack: PostgreSQL (non-superuser app role so row-level security is exercised),
  Redis, MinIO, Mailpit.
