# UI & Design Direction

> Status: **Direction set 2026-09-16** from reference material supplied by the product owner.
> Applies from checklist M1.3 (frontend skeleton) onward. Read with
> [CHECKLIST.md](CHECKLIST.md) and [CONVENTIONS.md](CONVENTIONS.md) §5.

---

## 1. The instruction

> "Login portal etc. must be creative and attractive — don't fill in basic setup."

The entry points to this product are not scaffolding. A pharmacy owner decides whether this looks
like real software in the first five seconds, and that judgement happens on the login screen, the
tenant picker and the empty dashboard — **before** they have any data to look at.

No default framework starter screens. No unstyled `<form>` on a white page. No "Django
administration" aesthetic anywhere a customer can reach.

## 2. Two registers, one system

This product has two kinds of screen and they are allowed to look different, as long as they share
one set of tokens, one type scale and one component library.

| | **Showcase** | **Operational** |
|---|---|---|
| Screens | Login, 2FA, tenant picker, invite acceptance, onboarding wizard, dashboards, empty states, upgrade prompts, platform console home, marketing site | POS billing, purchase entry, stock lists, registers, reports, ledgers |
| Priority | Impression, clarity, confidence | Speed, density, accuracy |
| Style | Generous whitespace, soft gradients, depth, illustration, motion | Compact rows, tabular figures, status chips, minimal chrome, near-zero motion |
| Success test | "This looks like serious software" | "I billed 200 customers today without thinking about the UI" |

The mistake to avoid is letting the showcase style leak into the POS (slow, airy, mouse-driven) or
letting the operational style leak into the login (grey, flat, forgettable).

## 3. Visual language (from the reference material)

- **Layout.** Left sidebar with grouped sections and a collapse control; breadcrumb + page title +
  action cluster at top right; content as cards on a tinted page background, not boxes on flat white.
- **Cards.** Generous radius (12–16px), hairline border, very soft shadow. Cards carry a title, a
  quiet subtitle, an optional overflow menu.
- **KPI tiles.** Big number, a delta chip (up/down, coloured), a sparkline or small area chart, and
  a "vs. last week" comparison line. These sit in a row of four across the top of dashboards.
- **Colour.** Restrained neutral base; one accent used sparingly for the active state and primary
  action; soft pastel gradient fills inside charts. Status colour is reserved for meaning —
  expiry, stock-out, sync failure, compliance breach — and never used decoratively.
- **Filter tabs.** Pill-shaped segmented controls with a solid dark pill for the active item.
- **Tables.** Sortable headers, right-aligned tabular numerals, status chips, row actions on hover,
  a sticky header, and a clear selected-row state.
- **Depth and motion.** Subtle. A gradient backdrop and a floated, slightly rotated app window is
  the marketing register — not the in-app one.

## 4. The login portal specifically

It must carry the product's identity, not a form on a page. Working direction:

- A split canvas: the form on one side, an expressive branded panel on the other.
- The branded panel is **about pharmacy work** — expiry, compliance, stock, the counter queue — not
  generic stock photography or abstract blobs.
- Devanagari and Latin both set well; the language toggle is visible before sign-in, because the
  person at the counter may not read English.
- Honest states: a clear offline indicator, and a visible sync-pending count if the device has
  unsynced bills. A pharmacist must never be unsure whether their bills reached the server.
- Trust signals sized for this market: DDA/IRD readiness, data-held-in-Nepal, the version number.
- It must still be fast and keyboard-complete. Attractive does not mean heavy: no large video, no
  blocking web font, and it must render acceptably on a 4 GB Windows 10 machine.

Related surfaces held to the same standard: 2FA, password reset, invitation acceptance, tenant
picker, onboarding wizard, subscription-lapsed (read-only) screen, and every first-run empty state.

## 5. Non-negotiables that constrain the design

These come from the domain, and they outrank aesthetics when they conflict.

1. **POS speed.** Add an item in under 300 ms, complete a bill in under 5 s, fully keyboard-driven.
   Any animation on the billing path must be removable.
2. **Devanagari.** Nepali is a first-class language, not an afterthought translation. Line height
   and font stack must be chosen for Devanagari from the start, and layouts must survive longer
   Nepali strings.
3. **Low-end hardware and small screens.** 1366×768 is the common counter resolution; 4 GB RAM and
   an HDD are common. Budget accordingly.
4. **Offline is visible.** Connection and sync state are permanent UI, not a toast.
5. **Accessibility.** WCAG 2.1 AA. Status must never be conveyed by colour alone — an expiry
   warning needs an icon or text, because colour-blind pharmacists dispense medicines too.
6. **Regulatory surfaces are plain.** Registers, tax invoices and the DDA inspection package follow
   the prescribed format. They are printed and inspected; they are not a place for design
   expression.

## 6. How this gets built

Per CONVENTIONS §5, all of this lives in `@npms/ui` (shadcn/ui + Tailwind + design tokens) with
Storybook. Screens compose that library; they do not hand-roll styles. The showcase/operational
split is expressed through tokens (density, radius, motion) rather than through two codebases.

Open items for M1.3: brand identity (name, logo, palette) is not yet decided — see checklist M0.3.
Until it is, build against neutral tokens so the brand can be swapped in one place.
