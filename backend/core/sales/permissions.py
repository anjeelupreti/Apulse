"""Sales permissions.

Split finely on purpose. Building a bill, issuing it, cancelling it and crediting it are four
different levels of trust: an assistant may build and issue, and neither cancelling a tax document
nor handing money back belongs to whoever happens to be on the counter.
"""

from kernel.rbac.registry import register

INVOICE_VIEW = register("sales.invoice.view", "View bills", "बीजक हेर्ने", is_read_only=True)
INVOICE_BUILD = register(
    "sales.invoice.build",
    "Build a bill",
    "बीजक तयार गर्ने",
    description="Start a draft and put items on it. Moves no stock and takes no number.",
)
INVOICE_ISSUE = register(
    "sales.invoice.issue",
    "Issue a bill",
    "बीजक जारी गर्ने",
    description="Takes the invoice number and moves the stock. After this nothing on it changes.",
)
INVOICE_CANCEL = register(
    "sales.invoice.cancel",
    "Cancel an issued bill",
    "जारी बीजक रद्द गर्ने",
    description="Reverses the stock and issues the credit note that evidences the cancellation.",
)
INVOICE_DISCOUNT = register("sales.invoice.discount", "Give a discount on a line", "छुट दिने")
INVOICE_REPRINT = register(
    "sales.invoice.reprint",
    "Reprint a bill",
    "बीजक पुनः छाप्ने",
    description="Every copy after the first is counted and marked as a copy.",
)

CREDIT_NOTE_VIEW = register(
    "sales.credit_note.view", "View credit notes", "क्रेडिट नोट हेर्ने", is_read_only=True
)
CREDIT_NOTE_ISSUE = register(
    "sales.credit_note.issue",
    "Issue a credit note",
    "क्रेडिट नोट जारी गर्ने",
    description="Takes money back off a bill. Cannot be undone except by another credit note.",
)
RETURN_TO_SHELF = register(
    "sales.credit_note.return_to_shelf",
    "Put returned stock back on the shelf",
    "फिर्ता सामान पुनः बिक्रीमा राख्ने",
    description=(
        "Returns go to quarantine by default. Only somebody who can judge whether a pack was "
        "kept properly should be able to put it back."
    ),
)
