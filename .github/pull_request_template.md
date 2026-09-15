## What and why

<!-- What changes, and the problem it solves. Link the checklist milestone, e.g. M2.3, and any issue. -->

## Release note

<!-- One customer-facing line (en). Leave "none" for internal-only changes. -->

## Screenshots / API examples

<!-- UI changes: before and after. API changes: a sample request and response. -->

## Migration and rollout notes

<!-- New migrations? Backward compatible with the currently deployed release? Data backfill needed?
     Behind a feature flag? Anything support should know before this ships? -->

## Checklist

- [ ] Tests added or updated; `python tasks.py lint` and `python tasks.py test` pass locally
- [ ] Tenant-isolation test added for any new tenant-scoped endpoint
- [ ] Permissions and feature gates declared; authorisation enforced server-side
- [ ] Audit events emitted for writes
- [ ] i18n keys added for both `en` and `ne` (no hardcoded user-visible strings)
- [ ] OpenAPI schema regenerated if the API changed
- [ ] Migrations are backward compatible (expand → migrate → contract)
- [ ] Docs / changelog updated
- [ ] No secrets, no production data, no tool-attribution trailers
- [ ] Any regulatory rule implemented here is backed by a verified entry in the compliance register
