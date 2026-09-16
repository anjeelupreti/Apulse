# Competitor and Market Notes

> Researched 2026-09-16 from public marketing material. Vendor claims are **marketing, not
> verified fact** — feature lists say what a vendor chooses to advertise, and silence about a
> capability is not proof it is missing. Useful for positioning and for spotting gaps; not a
> substitute for a hands-on trial (checklist M0.2).

---

## Okhati — the closest comparison

[okhati.com.np](https://okhati.com.np/) · Nepali company, cloud-based.

Positioned as a **suite across five products**: Clinic, Pharmacy, Hospital, Dental and Lab. That
shape is worth noticing, because it is the same bet this project is making — one platform, several
health verticals, sold separately — and it is being made by a company that already has Nepali
customers.

Advertised pharmacy capabilities:

- Real-time inventory with **stock and expiry alerts**
- Fast sales and billing, pitched explicitly at reducing human error
- Supplier, order and payment tracking
- Sales history, purchase records and current stock
- Customisable reports
- Cloud backup, accessible from any device
- **Direct links with clinics and hospitals** for sharing data

Advertised clinic capabilities: appointment scheduling, EMR, billing and invoicing, client ledger,
and a mobile app for doctors to read and update patient history.

Sources: [product site](https://okhati.com.np/),
[pharmacy blog post](https://okhati.com.np/blog/digital-pharmacy-management-software-nepal),
[clinic blog post](https://okhati.com.np/blog/okhati-nepals-popular-clinic-management-solution)

### What their marketing does **not** claim

Read carefully, the pharmacy page talks about inventory, billing and reporting — and does not
mention **DDA compliance, the drug schedules, a narcotic register, IRD/CBMS e-billing, or
prescription enforcement**. Nor does it mention offline operation.

Two readings, and the honest answer is that both are possible:

1. Those capabilities exist but are not what they lead with, because owners buy on speed and price.
2. They are genuinely thin, and compliance is where a regulation-first product can differentiate.

**Do not assume the second.** The next step is a hands-on trial or a conversation with a pharmacy
that uses it. Positioning a product against a competitor's advertised silence is how you end up
claiming a gap that closed a year ago.

## Indian systems named in the BRD

Marg ERP, Gofrugal, eVitalRx and others are Indian products. Their pharmacy features map to Indian
regulation — Schedule H/H1, GST, DL numbers — which **does not transfer to Nepal**. Samuha
क/ख/ग is not Schedule H, VAT is not GST, and CBMS is not the GST Network.

They remain useful for *workflow* ideas, which travel well: ERP-to-ERP ordering between pharmacy and
distributor, refill reminders tied to prescription duration, promise orders for out-of-stock items,
short-book, and substitute suggestion by salt. The regulatory layer has to be built for Nepal
regardless of which of them is copied.

The BRD also cited "Midas" and "Danfee". Neither resolves to an identifiable pharmacy product in
search; "Danfee" is most likely **Danphe EMR** (open-source hospital software used in Nepal,
India and Bangladesh). **Treat both names as unverified** and drop them from any comparison table
until someone confirms what was meant.

## Where this product is actually differentiated

Based on what is built rather than what is planned:

| | Typical advertised offering | This system |
|---|---|---|
| Expiry | Alerts | **Expired stock cannot be sold at all**; nearest-expiry batch is chosen automatically |
| Audit | Backups | **Hash-chained, append-only**; the database refuses to alter history |
| Multi-branch | Multi-location | **Database-enforced isolation**, tested against cross-tenant access |
| Numbering | Invoice numbers | **Gapless per branch and fiscal year**, frozen once issued, leasable to offline counters |
| Tax | VAT support | **No default tax category**, because the Gazette decides, not the software |

These are the things that are hard to retrofit and hard to fake in a demo. They are also invisible
to a buyer in a fifteen-minute sales call, which is a marketing problem to solve later, not a
reason to build less of them.

## Open questions for field research (M0.2)

1. What do pharmacies using Okhati actually complain about?
2. Does anything on the market handle the narcotic register digitally, and do pharmacies trust it?
3. How many pharmacies are above the NPR 10 crore e-billing threshold? Below it, CBMS is a
   selling point rather than a requirement.
4. What do pharmacies do today when the internet is down? If the honest answer is "write a paper
   bill", then offline-first is worth more than any feature list.
5. Price points actually paid, as opposed to list prices.
