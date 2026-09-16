# Nepal Regulatory Findings

> Researched 2026-09-16. **These are secondary sources** — law-firm summaries, vendor guides and DDA
> page titles — not the Gazette or the Acts themselves. They narrow the open questions in
> [COMPLIANCE_REGISTER.md](../COMPLIANCE_REGISTER.md) and point at the primary documents to obtain;
> they do not close them. Nothing here should be coded as a rule until the primary text is in hand.

---

## 1. The document the BRD called "CSDD 2024"

It appears to be **औषधि बिक्रि वितरण संहिता, २०८०** — the *Drug Sale and Distribution Code, 2080*,
published by the Department of Drug Administration.
Source: [dda.gov.np](https://dda.gov.np/content/194/drug-sale-and-distribution-code---2080/)

2080 BS corresponds to 2023/24 AD, which fits "CSDD 2024". The BRD's "16 components and 121
indicators" is plausible but **unverified** — the page serves the text as a download rather than as
HTML, so the structure could not be read.

**Action:** download the PDF from the DDA site and transcribe the components and indicators into
`backend/modules/pharmacy_compliance/fixtures/`. This is the single most valuable document for the
compliance module. Related codes referenced by DDA: GMP, GPP (Good Pharmacy Practice) and GSDP.

## 2. Drug classification — समूह क / ख / ग

Reported consistently in Nepali coverage of DDA rules:

| Group | Nepali | Rule as reported |
|-------|--------|------------------|
| Ka | समूह क | **Prescription required** |
| Kha | समूह ख | **Prescription required** |
| Ga | समूह ग | May be supplied on a **pharmacist's advice** |

**This differs from the BRD**, which treated Ka as narcotics-only and Ga as freely sellable OTC.
Both क and ख appear to require a prescription, and ग is explicitly tied to a pharmacist's advice
rather than being unrestricted self-service.

The drug rules engine already models this as versioned data with per-group required actions, so the
correction is a rule-set change rather than a code change. **The official group lists are still
needed** (CR-DDA-01).

## 3. VAT on medicines — the answer is conditional

**VAT Act, 2052, Schedule 1, Group 4(क):**

> "श्री ५ को सरकारले नेपाल राजपत्रमा सुचना प्रकाशन गरी तोकिदिएका औषधि तथा स्वास्थ्य सेवाहरु"
> — *medicines and health services designated by the Government by notice published in the Nepal
> Gazette.*

Source: [actnepal.com — Schedule 1](https://actnepal.com/en/schedule/3/2/vat-exempt-goods-and-services)

So exemption is **not automatic for everything a pharmacy sells**. It applies to what has been
gazetted. A pharmacy's shelf will therefore contain both exempt and standard-rated stock, and the
classification per item is a real decision, not a formality.

**This validates the design already built:** every item must name a tax category and there is no
default. Had the system assumed "medicines are exempt", cosmetics, supplements and devices would
have been under-taxed.

**Action:** obtain the Gazette notice listing designated medicines (CR-IRD-01). Until then, tax
classification during onboarding must be done against that list by the pharmacy's accountant.

## 4. IRD e-billing — requirements that match what is built

Reported under the **Electronic Billing Procedure, 2074** (4th amendment):

| Requirement as reported | State in this system |
|---|---|
| Approval required above **NPR 10 crore** turnover (NPR 5 crore for hospitality) | Threshold gating not yet built (control plane) |
| Real-time or scheduled sync to **CBMS** | Adapter not yet built (M7.2) |
| **Fiscal-year based invoice numbers**, with reprint labelling | ✅ Built — series per branch per fiscal year; reprint counter still to come |
| **Immutable audit trail, no hard deletes**; every edit records user, time and reason | ✅ Built — append-only audit chain and append-only stock ledger |
| Data **hosted in Nepal**, or with local backup accessible to IRD | Decided in the architecture; not yet provisioned |

Sources: [mis.ac](https://mis.ac/articles/blog/electronic-billing-cbms-nepal.php),
[ebillingnepal.com](https://ebillingnepal.com/en/articles/legal-provision-for-e-billing-nepal)

The approval process reportedly involves IRD inspecting the software and issuing a certificate,
with the vendor submitting sample invoices, a user manual and the technical architecture.

**Action:** obtain the Electronic Billing Procedure 2074 and its amendments as primary text
(CR-IRD-04), and the CBMS API specification (CR-IRD-07).

## 5. Pharmacy licensing has moved to the provinces

A DDA notice is titled *"प्रदेश स्तरमा हुने फार्मेसी (औषधि) पसल दर्ता प्रमाणपत्र नवीकरण तथा व्यवसायी मान्यता
प्राप्त कार्ड नवीकरण"* — **province-level** pharmacy shop registration certificate renewal, and
renewal of the practitioner recognition card.
Source: [dda.gov.np](https://dda.gov.np/content/150/pharmacies--medicine--shop-registration-certificate-and-businessmen/)

**The BRD assumed central DDA licensing.** Retail registration and renewal appear to sit with the
province, with DDA retaining the central role. The notice body is published as an image, so
validity periods, deadlines and fees could not be read.

**Design consequence:** a branch's licence record needs the **issuing authority** (which province,
or DDA centrally), not just a number and an expiry date. Two branches of one chain in different
provinces may renew with different offices on different cycles. The `Branch` model already carries
province and district, so this is an added field rather than a restructure.

## 6. DAMS — the DDA's own system

**DAMS (Drug Administration Management System)** is the DDA's central database. A notice marked
*अत्यन्त जरुरी* (extremely urgent) requires manufacturing licences and **drug sale/distribution
registration certificates to be entered into it**.
Source: [dda.gov.np](https://dda.gov.np/content/179/essential-notice-for-dams-entry/)

**This was not in the BRD at all.** It is both an obligation on every pharmacy and a potential
integration: if DAMS exposes an interface, licence status and registered-drug data could be
verified rather than typed. Worth investigating before building a manual licence register.

## 7. Narcotics

Under the **Narcotic Drugs (Control) Act, 2033**, a seller of narcotic drugs must keep records in a
**prescribed format**, with the **doctor's prescription attached** to the record.
Source: [nitipartners.com](https://nitipartners.com/narcotics-control-act-nepal/)

This matches the digital narcotic register already specified: register entry plus a linked
prescription image. **The prescribed format itself is still needed** (CR-DDA-02) — "prescribed"
means a form set out in the rules, and the register must match it column for column to be accepted.

---

## What changes as a result

| Finding | Effect |
|---------|--------|
| Group क **and** ख both need a prescription | Correct the drug rule set; no code change needed |
| VAT exemption is by Gazette list, not by being a medicine | Confirms the "no default tax category" decision |
| Licensing is province-level | Add issuing authority to the branch licence record |
| DAMS exists and is mandatory | Investigate before building a manual licence register |
| E-billing demands an immutable trail and fiscal-year numbering | Already built; keep it that way |

## Primary documents still to obtain

1. औषधि बिक्रि वितरण संहिता २०८० (full PDF) — the compliance module depends on it
2. Gazette notice of VAT-exempt medicines
3. Official समूह क / ख / ग drug lists
4. Electronic Billing Procedure 2074 with amendments, and the CBMS API specification
5. The prescribed narcotic register format
6. Province-level registration rules: validity, renewal window, fees
7. DAMS: what it exposes, and whether it can be integrated with
