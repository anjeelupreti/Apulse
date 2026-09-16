"""Document types this module numbers."""

from kernel.numbering.registry import register

SALES_INVOICE = "sales.invoice"

register(
    SALES_INVOICE,
    "Tax invoice",
    "कर बीजक",
    abbreviation="INV",
    is_tax_document=True,
    description="The invoice given to the customer. Numbering is what IRD inspects first.",
)

CREDIT_NOTE = "sales.credit_note"

register(
    CREDIT_NOTE,
    "Credit note",
    "क्रेडिट नोट",
    abbreviation="CN",
    is_tax_document=True,
    description=(
        "Issued when an invoice is reduced or undone. A sale is never deleted, so this is the "
        "only lawful way money comes back off a bill."
    ),
)
