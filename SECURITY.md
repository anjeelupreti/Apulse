# Security Policy

This platform stores health and tax records for regulated businesses. Treat every security issue as
affecting real patients and real pharmacy licences.

## Reporting a vulnerability

Email **security@<domain-to-be-registered>** with:

- what you found and where,
- steps to reproduce (or a proof of concept),
- the impact you believe it has.

Please do **not** open a public issue, and do not test against production tenants. We aim to
acknowledge within 2 business days and to ship a fix or mitigation for high-severity issues within
7 days.

> TODO (M0.4): replace the placeholder address once the company domain is registered, and publish a
> PGP key.

## Scope

In scope: the API, the tenant web app, the platform console, the desktop POS, deployment
configuration in this repository.

Out of scope: third-party services we integrate with (report those to their owners), findings that
require physical access to a pharmacy's machine, and denial of service via volumetric traffic.

## Handling rules for contributors

- Never copy production data to a laptop or a non-production environment.
- Never commit secrets. `gitleaks` runs in pre-commit and in CI, but it is a backstop, not a gate.
- Report any suspected exposure of patient data, prescriptions or credentials immediately; do not
  attempt to clean it up silently.
