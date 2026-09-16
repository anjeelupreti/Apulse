"""Invoice arithmetic, kept free of the database so it can be read and tested on its own.

The awkward part is that a Nepali pharmacy prices at MRP, and MRP already contains any tax. So the
usual "add tax to the price" is backwards here: the tax has to be extracted from a price the
customer already sees printed on the pack.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from shared.formatting import quantize_money

#: Counters deal in whole rupees, so totals round to the nearest rupee by default and the
#: difference is shown on the invoice rather than hidden in a line.
DEFAULT_ROUNDING_STEP = Decimal("1")
NO_ROUNDING = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class LineAmounts:
    gross: Decimal
    discount: Decimal
    net: Decimal
    taxable: Decimal
    tax: Decimal

    @property
    def total(self) -> Decimal:
        return self.taxable + self.tax


def compute_line(
    *,
    quantity: Decimal,
    rate: Decimal,
    discount_percent: Decimal = Decimal("0"),
    tax_percentage: Decimal = Decimal("0"),
    price_includes_tax: bool = True,
) -> LineAmounts:
    """What one line comes to.

    With `price_includes_tax`, the rate is what the customer pays and the tax is inside it.
    Without it, tax is added on top — which is how a wholesale invoice to another business works.
    """
    gross = quantize_money(quantity * rate)
    discount = quantize_money(gross * discount_percent / 100)
    net = gross - discount

    if tax_percentage == 0:
        return LineAmounts(
            gross=gross, discount=discount, net=net, taxable=net, tax=Decimal("0.00")
        )

    if price_includes_tax:
        taxable = quantize_money(net / (1 + tax_percentage / 100))
        tax = net - taxable
    else:
        taxable = net
        tax = quantize_money(net * tax_percentage / 100)

    return LineAmounts(gross=gross, discount=discount, net=net, taxable=taxable, tax=tax)


@dataclass(frozen=True, slots=True)
class InvoiceTotals:
    gross: Decimal
    discount: Decimal
    taxable: Decimal
    tax: Decimal
    subtotal: Decimal
    rounding: Decimal
    payable: Decimal


def compute_totals(
    lines: list[LineAmounts], *, rounding_step: Decimal = DEFAULT_ROUNDING_STEP
) -> InvoiceTotals:
    """Add the lines up and round the amount actually handed over.

    Rounding is applied once, to the total, and recorded separately. Rounding each line instead
    would make the invoice's own arithmetic fail to add up, which an auditor will notice.
    """
    gross = quantize_money(sum((line.gross for line in lines), Decimal("0")))
    discount = quantize_money(sum((line.discount for line in lines), Decimal("0")))
    taxable = quantize_money(sum((line.taxable for line in lines), Decimal("0")))
    tax = quantize_money(sum((line.tax for line in lines), Decimal("0")))
    subtotal = taxable + tax

    payable = (subtotal / rounding_step).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    ) * rounding_step
    payable = quantize_money(payable)

    return InvoiceTotals(
        gross=gross,
        discount=discount,
        taxable=taxable,
        tax=tax,
        subtotal=subtotal,
        rounding=payable - subtotal,
        payable=payable,
    )
