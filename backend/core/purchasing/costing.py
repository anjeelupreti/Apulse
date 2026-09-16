"""Working out what stock actually cost.

Kept free of the database so the arithmetic can be read and tested on its own. Three things make
this harder than quantity times rate:

* **Bonus quantity.** Eleven units arrive and ten are charged for, so all eleven cost less.
  Ignoring the free one overstates cost and understates margin on every sale from that batch.
* **Freight.** Charges on the invoice belong to the stock, spread across the lines.
* **Recoverable VAT.** A VAT-registered pharmacy reclaims input VAT, so it is not part of cost.
  One that is not registered pays it and never gets it back, so it is.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

COST_DECIMALS = 4
_COST_STEP = Decimal(1).scaleb(-COST_DECIMALS)


def quantize_cost(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_COST_STEP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class LineCosting:
    """What one received line cost, per base unit."""

    charged_base_quantity: Decimal
    free_base_quantity: Decimal
    net_amount: Decimal
    freight_share: Decimal
    non_recoverable_tax: Decimal

    @property
    def total_base_quantity(self) -> Decimal:
        """Everything that physically arrived, paid for or not."""
        return self.charged_base_quantity + self.free_base_quantity

    @property
    def total_cost(self) -> Decimal:
        return self.net_amount + self.freight_share + self.non_recoverable_tax

    @property
    def unit_cost(self) -> Decimal:
        if self.total_base_quantity == 0:
            return Decimal("0")
        return quantize_cost(self.total_cost / self.total_base_quantity)

    @property
    def unit_cost_ignoring_bonus(self) -> Decimal:
        """What the cost would look like if the free units were not counted.

        Only useful for showing a buyer what the deal is worth.
        """
        if self.charged_base_quantity == 0:
            return Decimal("0")
        return quantize_cost(self.total_cost / self.charged_base_quantity)

    @property
    def bonus_saving_percent(self) -> Decimal:
        """How much the free quantity brings the unit cost down, as a percentage."""
        without = self.unit_cost_ignoring_bonus
        if without == 0:
            return Decimal("0")
        return quantize_cost((without - self.unit_cost) / without * 100)


def cost_line(
    *,
    charged_base_quantity: Decimal,
    free_base_quantity: Decimal,
    net_amount: Decimal,
    freight_share: Decimal = Decimal("0"),
    tax_amount: Decimal = Decimal("0"),
    vat_is_recoverable: bool,
) -> LineCosting:
    return LineCosting(
        charged_base_quantity=charged_base_quantity,
        free_base_quantity=free_base_quantity,
        net_amount=net_amount,
        freight_share=freight_share,
        non_recoverable_tax=Decimal("0") if vat_is_recoverable else tax_amount,
    )


def allocate_freight(freight: Decimal, line_amounts: list[Decimal]) -> list[Decimal]:
    """Spread a delivery charge across lines in proportion to their value.

    The last line absorbs the rounding difference, so the shares always add back to the freight
    charged. Losing a paisa here would leave the stock valuation permanently out by that much.
    """
    total = sum(line_amounts)
    if freight == 0 or total == 0:
        return [Decimal("0.00") for _ in line_amounts]

    shares = [
        (amount / total * freight).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for amount in line_amounts
    ]
    shares[-1] += freight - sum(shares)
    return shares
