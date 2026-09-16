# Compliance Register — Claims to Verify Before Build

> The BRD contains regulatory statements that **must be verified against primary sources** (Gazette, DDA, IRD, NPC, MoHP notices) before they are coded as rules. Wrong compliance logic is worse than none.
> Each item needs: primary source link/scan, date checked, verifier name, outcome, and resulting rule config.

Legend: ⬜ Not verified · 🟨 In progress · ✅ Verified · ❌ Incorrect (update BRD)

## IRD / Tax

| ID | Claim / Question | Why it matters | Status |
|----|------------------|----------------|--------|
| CR-IRD-01 | **Are medicines VAT-exempt** under VAT Act 2052 Schedule 1? BRD assumes 13% VAT on all sales. Which items (cosmetics, supplements, devices, baby food, sanitary goods) are taxable? | Tax engine defaults; wrong VAT = legal & customer harm | ⬜ |
| CR-IRD-02 | Turnover threshold for mandatory IRD-approved e-billing software (BRD: > NPR 10 crore) — current value & effective date | Plan gating / sales messaging | ⬜ |
| CR-IRD-03 | Turnover threshold for real-time CBMS sync (BRD: > NPR 25 crore) and whether voluntary sync is allowed below it | CBMS adapter scope | ⬜ |
| CR-IRD-04 | Current **IRD e-billing software approval/certification** procedure: required features (no bill delete, cancel via credit note, reprint "Copy of Original" counter, audit log, materialized view, sales/purchase registers, backup), documents, audit fee, timeline | Blocks go-live for thresholded customers | ⬜ |
| CR-IRD-05 | Exact mandatory invoice fields & format for tax invoice vs abbreviated invoice (BRD says 11 fields); buyer PAN requirement threshold (BRD: ≥ NPR 10,000) | Invoice templates | ⬜ |
| CR-IRD-06 | Is **offline billing with pre-leased per-device number ranges** acceptable (non-contiguous series per branch)? Or must series be per counter with distinct prefixes? | Offline POS design (ADR-0004) | ⬜ |
| CR-IRD-07 | CBMS API spec: endpoints, auth, payload, credit note format, retry rules, sandbox access process | Adapter build | ⬜ |
| CR-IRD-08 | Record retention period for billing records (years) | Retention engine | ⬜ |
| CR-IRD-09 | TDS rules relevant to pharmacy purchases/services; Annex/purchase-sales book formats | Accounting reports | ⬜ |
| CR-IRD-10 | Fiscal year boundaries & invoice series reset rules | Numbering service | ⬜ |

## DDA / Drug Act

| ID | Claim / Question | Status |
|----|------------------|--------|
| CR-DDA-01 | Samuha KA/KHA/GA definitions & official drug lists (per Drug Act 2035 and rules); machine-readable source? | ⬜ |
| CR-DDA-02 | Narcotic/psychotropic register mandatory fields & retention period (BRD cites Section 33 — verify section) | ⬜ |
| CR-DDA-03 | "DDA 2026 update": Pregabalin prescription-mandatory; Dicyclomine & Promethazine retail record keeping — obtain notice | ⬜ |
| CR-DDA-04 | Local government recommendation letter requirement for pharmacy licence (BRD: new from 2026) | ⬜ |
| CR-DDA-05 | Pharmacy licence validity & renewal window (BRD: 2 years; renewal within 35 days) | ⬜ |
| CR-DDA-06 | CSDD 2024: obtain official document — exact 16 components & **121 indicators** text, scoring method | ⬜ |
| CR-DDA-07 | ADR reporting form format & submission channel to DDA (national pharmacovigilance centre) | ⬜ |
| CR-DDA-08 | Recall notice format/channel; required pharmacy actions & timelines | ⬜ |
| CR-DDA-09 | Retail/wholesale **margin caps** & price ceilings on specific drugs; MRP display rules | ⬜ |
| CR-DDA-10 | DDA product registration number requirement on purchase/sale records; import licence data | ⬜ |
| CR-DDA-11 | GSDP guideline: temperature zones, humidity records, excursion handling, self-inspection checklist | ⬜ |
| CR-DDA-12 | Pharmacist/assistant presence requirements per Samuha category (who may dispense what) | ⬜ |
| CR-DDA-13 | Narcotic Drugs (Control) Act 2033 — wholesale/retail quotas, reporting to authorities | ⬜ |
| CR-DDA-14 | Prescription validity duration and repeat dispensing rules | ⬜ |
| CR-DDA-15 | Hospital Pharmacy Service Guideline 2015 (or newer) requirements | ⬜ |

## Professional Councils

| ID | Claim / Question | Status |
|----|------------------|--------|
| CR-NPC-01 | Nepal Pharmacy Council registration number format; any public verification API/portal | ⬜ |
| CR-NMC-01 | NMC doctor registration number format; public lookup availability (NDC for dentists, NHPC for others) | ⬜ |
| CR-NPC-02 | CPD requirements for pharmacists (hours, categories) | ⬜ |

## Privacy / Data

| ID | Claim / Question | Status |
|----|------------------|--------|
| CR-PRIV-01 | Individual Privacy Act 2075 & Regulations — consent, health data handling, breach notification | ⬜ |
| CR-PRIV-02 | Data residency obligations for health & tax data (must servers be in Nepal?) | ⬜ |
| CR-PRIV-03 | Electronic Transactions Act 2063 — digital signature validity for e-invoices/registers | ⬜ |
| CR-PRIV-04 | SMS/WhatsApp marketing consent rules (NTA directives) | ⬜ |

## Payments & Integrations

| ID | Claim / Question | Status |
|----|------------------|--------|
| CR-PAY-01 | eSewa / Khalti / Fonepay / ConnectIPS merchant onboarding for a SaaS platform (aggregator vs per-tenant merchant) | ⬜ |
| CR-PAY-02 | NRB rules on storing payment references / reconciliation | ⬜ |
| CR-INS-01 | SSF & Health Insurance Board claim integration specs | ⬜ |

## Reference Data

| ID | Claim / Question | Why it matters | Status |
|----|------------------|----------------|--------|
| CR-CAL-01 | Authoritative **Bikram Sambat month-length table** (days in each of the 12 months, per BS year) with a verified Gregorian anchor for Baisakh 1 — from Nepali Patro, the Department of Survey, or an equivalent published source | There is no formula for BS; the lengths are published, not computed. A month one day out shifts the date printed on every later tax invoice and can move a sale into the wrong fiscal year, which is a filing error. **No table is bundled**: the engine, the loader and the validators are built, and `manage.py validate_bs_calendar <file>` checks any candidate table and prints its New Year dates for line-by-line comparison. The drift check catches accumulated errors but *cannot* catch a single year that is one day out and corrected the next, so a published source is still required. Set `BACKEND_BS_CALENDAR_FILE` once verified | ⬜ |
| CR-GEO-01 | Official list of Nepal's **77 districts and 753 local levels** (bilingual, with type: metropolitan / sub-metropolitan / municipality / rural municipality) from CBS or MoFAGA | Branch addresses appear on tax invoices, DDA licence records and inspection packages; a misspelled or invented place name is a defect in a legal document. The 7 provinces are seeded; districts and local levels are deliberately **not**, pending this file. Load with `manage.py import_geo --districts … --local-levels …` | ⬜ |

## BRD Numbers to Source or Remove

| ID | Claim | Status |
|----|-------|--------|
| CR-SRC-01 | "2025 Hetauda Hospital study — 61.2% CSDD compliance" — obtain citation | ⬜ |
| CR-SRC-02 | Samuha KA "9 narcotics, 22 psychotropics" count | ⬜ |
| CR-SRC-03 | Competitor facts (Marg user count, eVitalRx ONDC, MediFlux pricing, Danphe hospital count) — re-verify before any marketing use | ⬜ |
