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
