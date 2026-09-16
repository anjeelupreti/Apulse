"""Document types this module numbers."""

from kernel.numbering.registry import register

GOODS_RECEIPT = "purchasing.goods_receipt"

register(
    GOODS_RECEIPT,
    "Goods received note",
    "सामान प्राप्ति नोट",
    abbreviation="GRN",
    description="Records what a supplier actually delivered, against their invoice.",
)
