"""Nepali notes and coins, and counting a drawer with them.

Kept free of the database so the arithmetic can be read on its own.
"""

from collections.abc import Mapping
from decimal import Decimal

#: What is actually in circulation, largest first — the order a drawer is counted in.
#: Rs 1 and Rs 2 survive as coins and still turn up in a till, so they are here.
DENOMINATIONS: tuple[int, ...] = (1000, 500, 100, 50, 20, 10, 5, 2, 1)

#: Below this, a shift closes without anybody having to write an explanation. A rupee either way
#: on a day of cash handling is a rounding artefact, not a discrepancy, and demanding a paragraph
#: for it only teaches people to type "ok" into the box.
VARIANCE_TOLERANCE = Decimal("1.00")


def is_valid(value: int) -> bool:
    return value in DENOMINATIONS


def count_total(counts: Mapping[int, int]) -> Decimal:
    """What a denomination sheet adds up to."""
    return sum(
        (Decimal(value) * count for value, count in counts.items()), start=Decimal("0")
    ).quantize(Decimal("0.01"))


def unknown_values(counts: Mapping[int, int]) -> tuple[int, ...]:
    return tuple(sorted(value for value in counts if not is_valid(value)))


def needs_explanation(variance: Decimal) -> bool:
    return abs(variance) > VARIANCE_TOLERANCE


def break_down(amount: Decimal | int) -> dict[int, int]:
    """The fewest notes and coins that make up an amount.

    For handing change and for suggesting a bank deposit breakdown. Paisa are dropped: nothing
    smaller than a rupee circulates, which is why invoices round to whole rupees in the first
    place.
    """
    left = int(Decimal(amount))
    result: dict[int, int] = {}
    for value in DENOMINATIONS:
        if left <= 0:
            break
        count, left = divmod(left, value)
        if count:
            result[value] = count
    return result
