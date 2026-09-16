from collections.abc import Iterator

import pytest

from kernel.numbering import registry

INVOICE = "sales.invoice"
CREDIT_NOTE = "sales.credit_note"


@pytest.fixture
def document_types() -> Iterator[None]:
    """Register the document types these tests use, without leaking them into other tests.

    Nothing registers document types yet: they belong to the modules that own the documents, and
    core.sales does not exist. Registering them here keeps the numbering tests honest about that.
    """
    saved = dict(registry._registry)
    registry._registry.clear()
    registry.register(
        INVOICE,
        "Tax invoice",
        "कर बीजक",
        abbreviation="INV",
        is_tax_document=True,
    )
    registry.register(
        CREDIT_NOTE,
        "Credit note",
        "क्रेडिट नोट",
        abbreviation="CN",
        is_tax_document=True,
    )
    try:
        yield
    finally:
        registry._registry.clear()
        registry._registry.update(saved)
