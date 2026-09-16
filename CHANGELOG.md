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
- Multi-tenancy (kernel): tenant registry, legal entities, branches with DDA licence fields, and
  stock locations; tenant context bound to both the application and the database session;
  PostgreSQL row-level security on every tenant-scoped table, enforced even for the table owner;
  tenant resolution by verified custom domain or subdomain; read-only enforcement for suspended
  accounts that still allows reading, printing and exporting regulatory records; idempotent tenant
  provisioning that creates a locked narcotics cabinet and a quarantine location for every branch.
- Nepal administrative divisions with an idempotent `import_geo` command; the seven provinces ship
  with the code.
- UI design direction recorded ahead of the frontend work (`docs/DESIGN_DIRECTION.md`).
- Authentication: sign in with an email address or a phone number; session cookies with a CSRF
  bootstrap endpoint; two-factor authentication with an authenticator app plus single-use recovery
  codes; lockout after repeated failures; a security log of every sign-in attempt; and
  `/api/v1/me/context` returning the user, tenant, memberships and branches in one call.
  Signing in on a tenant's own address requires an active membership of that tenant.
- Access control: a registry of every permission the code checks; twelve built-in roles seeded into
  each account, from Owner to DDA Inspector; roles scoped to the whole account, one business or one
  branch; assignments that can expire, for inspection visits and locum cover; and professional
  registrations (`UserCredential`), so actions that require a registered pharmacist stay closed to
  everyone else whatever their role. `/api/v1/me/context` now returns the caller's permissions.
- Audit trail: every recorded action is hash-chained to the one before it, per account, and the
  database refuses to update, delete or truncate the table. `verify_chain()` reports whether the
  trail is intact and, if not, exactly where it breaks. Changes are recorded field by field, with
  secrets shown as changed but never printed. Permission changes are recorded automatically.
- Modules and entitlements: modules are declared in code and synced into the database so plans can
  reference them; what an account may use resolves from its installed modules and granted features.
  Plans set the base, add-ons add to it, and a manual override replaces the result. Feature flags
  give a kill switch and staged rollouts. Account limits, such as how many branches a plan
  includes, are enforced in the service layer, so the ceiling holds however a branch is created.
  `/api/v1/me/context` now returns the account's features and limits alongside its permissions.
- Bikram Sambat: conversion between BS and Gregorian dates, Nepal's Shrawan-to-Ashadh fiscal year,
  and validators that check a calendar table before it is trusted. No calendar table ships with the
  code: the month lengths are published rather than calculated, and one wrong day would shift the
  date on every later invoice. Supply a verified table and check it with `validate_bs_calendar`.
- Nepali number formatting: 1,00,000 rather than 100,000, Devanagari numerals, rupee amounts, and
  totals written in words using lakh and crore, as a tax invoice requires.
- Document numbering: each branch gets its own run of invoice numbers per fiscal year, restarting
  at 1 on Shrawan 1, with the number format and the counter frozen once the first number has been
  issued. Offline counters are lent a block of numbers in advance so they can keep billing without
  a connection, and the server skips past anything it has lent.
- Tax categories with dated rates, so an old invoice is always re-priced at the rate it carried.
  Which category a medicine belongs to is deliberately not assumed: every item must be classified.
- The item catalogue. Stock is counted in base units — a tablet, a millilitre — and packs are
  conversions on top, so selling four tablets out of a strip and receiving twenty boxes of ten
  strips are the same arithmetic. Barcodes identify the pack, so scanning a box adds a box.
  Quantities read the way a storekeeper counts: "2 boxes 4 strips 7 tablets", not "247 tablets".
- Batches and the stock ledger. Every receipt, sale, adjustment and write-off is recorded, and the
  database refuses to change or delete those records; a mistake is corrected by a reversing entry.
  Stock is issued nearest-expiry-first, and expired or quarantined stock is never picked. Selling
  expired stock is refused outright, while writing it off or returning it stays possible.
- Suppliers and customers as a single record, since in a pharmacy they overlap.
- Goods receipts. A delivery is entered as a draft and moves no stock until it is posted; posting
  creates the batches, brings the stock in and numbers the document, all at once. Bonus quantity
  ("10 + 1 free") is treated as stock that lowers the cost of the whole line, delivery charges are
  spread across lines, and VAT is counted as cost only for a pharmacy that cannot reclaim it.
  Entering the same supplier invoice twice is refused, as is receiving stock that has already
  expired unless someone confirms it deliberately.
- The counter sale. A bill is built as a draft and moves no stock until it is issued; issuing takes
  the invoice number, sells the batch nearest to expiry first, and fixes the totals. Prices come
  from the price printed on the batch on the shelf, selling above it is refused, and tax is worked
  back out of the shelf price rather than added to it. Which batch each customer received is
  recorded, so a recall can be answered. Reprints are counted so copies can be marked, and
  cancelling an invoice puts the stock back while keeping the number.
- Prescribers: doctors, dentists and health workers with their council registration. A name read
  off a prescription pad is accepted without a legible registration number, because refusing the
  record would only lose the sale; a medicine that requires a registered prescriber is then refused
  at the counter until the number is there.
- The pharmacy module: what makes this a pharmacy rather than a shop. Medicines carry a generic
  name, strength, dosage form and their समूह — क, ख or ग — and the समूह decides what has to happen
  before the medicine is handed over. Antibiotics and narcotics are refused without a valid
  prescription; a prescription dated in the future, or past its end date, is not a valid one. A
  medicine nobody has classified yet is treated as the most restricted, because guessing the other
  way means handing over a controlled drug by mistake. The rules are dated, so a notice that
  changes a requirement is entered as a new rule rather than rewriting how last year's sales were
  judged, and a backdated sale is judged by the rule that applied on the day it happened. The
  check runs before the invoice number is taken, so a refused sale leaves no gap in the numbering.
  The counter can ask a bill what it still needs while it is being built. The seeded rules are
  marked unverified: the official group lists are still to be confirmed against the Act (CR-DDA-01).
- The controlled-drug register. Every narcotic that enters or leaves the cabinet is written down
  as it moves: the date, the patient, the prescriber and their registration number, the drug, the
  batch, the quantity, the running balance and the pharmacist who handed it over. Names are copied
  in as well as linked, so a page reads a year later exactly as it read on the day. Which समूह is
  registered comes from the dated rule rather than a list in the code, so a notice bringing another
  group in applies from its own date.

  The database refuses to change or delete a line. A mistake is corrected by a new line pointing
  at the old one, and the correction needs a reason — an unexplained correction in a narcotics
  register is worse than the error it corrects. Controlled stock must be put away in a locked
  cabinet, checked when it is received. Only a registered pharmacist may hand it over. A count of
  the cabinet needs a witness and records only the difference it found, and it has to say which
  batch it counted. The register is written inside the same transaction as the sale, so a
  controlled drug can never leave the shelf without its entry.

  The register the Act prescribes has a format, and that format is still to be obtained
  (CR-DDA-02): this holds everything a page needs, but it is not yet laid out as DDA lays it out.
- Credit notes and sales returns. A sale is never deleted and an issued bill is never edited, so
  the only way money comes back off a bill is a credit note against it, numbered in its own series
  per branch and per fiscal year. Cancelling an invoice now issues one, which is what makes the
  cancellation answerable in a tax audit: marking our own record cancelled is a change to our
  record, while the note is a document that says what was reversed and why.

  You cannot return more than was sold, counted against the invoice line, so two half-returns
  cannot add up to more than the whole. Stock comes back as the batch it went out as, because a
  recall is answered from the batch record. Returned medicine goes to quarantine by default: once
  a pack has left the premises nobody can say how it was kept, and putting it back on the shelf is
  a decision somebody makes deliberately. A credit note is priced at what was charged, never at
  today's price, or a refund quietly becomes a discount. A returned narcotic goes back into the
  controlled-drug register.
- Crediting a bill is now one click. A single call drafts the note, fills every line that has not
  already been credited, numbers it and issues it — but only when the caller confirms, because it
  produces a real numbered tax document and moves stock, and the only way back is another credit
  note the other way round. What the button will credit can be read before it is pressed. The
  invoice itself is never touched: it keeps its number, its lines and its totals, and the
  correction stands as a separate document.
- Nothing on an issued bill can be edited any more, including its totals. Lines were already
  refused; recalculating the totals was not, so an issued invoice could have been silently
  re-added-up into a figure different from the one the customer is holding. Cancelled bills are
  closed the same way.
- Everything leaves a trail. A model is declared as tracked once, next to the app it belongs to,
  and from then on every create, change and delete of it is recorded automatically — prices, tax
  rates, drug schedules, batches, prescribers, prescriptions, branches and their DDA licences,
  bills and credit notes, including drafts that were built, altered and abandoned before anybody
  paid. The entries that matter most are the ones nobody would have thought to add by hand.

  The stock ledger and the narcotic register are deliberately left out: both already are logs,
  append-only in the database and carrying the actor, the document and the reason, and tracking
  them would write every scan at the counter twice.

  Two faults in the older diffing came out while testing this. A decimal read back from the
  database compared unequal to the same amount held in memory, so saving an untouched row was
  recorded as a change; and a changed password compared equal to itself, because both sides were
  masked before they were compared, so the one fact worth keeping — that it changed, and when —
  was being thrown away. Both are fixed.
- Taking money, and counting it out. A bill can be settled across several methods at once — half
  in cash, half on a wallet, the rest on account — and the total is checked against what is still
  owed, so a mistyped second tender cannot leave the accounts holding money nobody claimed. Change
  comes only from cash, because handing it back on a card payment is one of the simplest ways to
  empty a till. A wallet or a card has to carry its transaction reference; cash does not.

  Refunds go against the credit note rather than the invoice: the note is the document that says
  money is owed back, and a refund with nothing behind it is indistinguishable from a till being
  emptied. Payments and cash movements are append-only in the database, like the stock ledger, and
  a mistake is corrected by recording its opposite.

  The till itself is the unit of accountability. One open shift per counter, enforced by the
  database, because a shortfall on a shared drawer belongs to everybody who touched it and so to
  nobody. Cash leaving the drawer for anything other than a refund needs a witness and a reason.
  Closing counts the drawer in Nepali notes and coins and keeps the sheet, not just the total —
  "twelve five-hundreds" is checkable and "6,000" is not. The difference between the count and the
  register is recorded and never adjusted away: a till short by four hundred rupees is a fact
  about the day. Anything beyond a rupee needs an explanation before the shift will close; a rupee
  either way closes quietly, because demanding a paragraph for a rounding artefact only teaches
  people to type "ok" into the box. A supervisor signs the count off separately, since a cashier
  counting their own drawer and approving their own count is one person however many buttons they
  press.
- Selling on account. Putting a bill on the customer's tab is not the money arriving: it records
  how the bill was settled at the counter, and the invoice stays fully outstanding until somebody
  actually pays. Counting it as received is how a receivables ledger comes to show nothing owed
  while the shop is owed a fortune.

  Two questions get asked, and they are different. The limit is how much exposure a customer is
  allowed; overdue is whether they pay at all. A customer well inside their limit who has settled
  nothing since Baisakh is the worse risk of the two, and either one blocks the sale. A zero limit
  means no credit, never unlimited. The position is worked out and returned before it is raised as
  an error, so the counter can say "you are 300 over and a bill from Shrawan is unpaid" instead of
  a bare no.

  An override needs a reason and a name, and is recorded as an override in the trail. One nobody
  signed is the same as no control at all, and one with no reason is worse than none: it looks
  like a control while teaching everybody that the box takes anything.

  A bill's due date is frozen onto it the moment it goes on account, taken from the customer's
  terms as they stood that day, so tightening their terms next year does not turn settled history
  into a list of late payments.

  Customers now have a statement — opening balance, bills as debits, payments and credit notes as
  credits, a running balance, ordered by business date — and an ageing split, because every
  collections conversation is "30,000 of it has been sitting since Ashadh" rather than "they owe
  40,000".
