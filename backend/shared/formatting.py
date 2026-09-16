"""Numbers and money the way they are written in Nepal.

Digits group in the South Asian style (1,00,000 rather than 100,000), and tax invoices must carry
the total in words, so that conversion has to use lakh and crore rather than million and billion.
"""

from decimal import ROUND_HALF_UP, Decimal

DEVANAGARI_DIGITS = "०१२३४५६७८९"
_ASCII_TO_DEVANAGARI = str.maketrans("0123456789", DEVANAGARI_DIGITS)
_DEVANAGARI_TO_ASCII = str.maketrans(DEVANAGARI_DIGITS, "0123456789")

CURRENCY_SYMBOL = "रू"
CURRENCY_CODE = "NPR"

_UNITS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TENS = (
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
)
#: South Asian scale: a lakh is 10^5 and a crore 10^7, so "million" never appears.
LAKH = 100_000
CRORE = 10_000_000


def to_devanagari_digits(text: str) -> str:
    """`2082-03-15` becomes `२०८२-०३-१५`. Only digits change."""
    return text.translate(_ASCII_TO_DEVANAGARI)


def to_ascii_digits(text: str) -> str:
    """The reverse, for reading numbers a user typed in Devanagari."""
    return text.translate(_DEVANAGARI_TO_ASCII)


def group_digits(value: Decimal | int | str) -> str:
    """Group in the South Asian style: last three digits, then pairs.

    12345678 becomes 1,23,45,678 — not 12,345,678, which a Nepali reader has to stop and decode.
    """
    text = str(value)
    negative = text.startswith("-")
    text = text.lstrip("-")

    whole, _, fraction = text.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        pairs: list[str] = []
        while len(head) > 2:
            pairs.insert(0, head[-2:])
            head = head[:-2]
        if head:
            pairs.insert(0, head)
        whole = ",".join([*pairs, tail])

    grouped = f"{whole}.{fraction}" if fraction else whole
    return f"-{grouped}" if negative else grouped


def quantize_money(amount: Decimal | int | str) -> Decimal:
    """Two decimal places, rounded half up — the rounding a cashier expects."""
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_npr(
    amount: Decimal | int | str, *, symbol: bool = True, devanagari: bool = False
) -> str:
    value = quantize_money(amount)
    negative = value < 0
    grouped = group_digits(abs(value))
    if devanagari:
        grouped = to_devanagari_digits(grouped)
    prefix = f"{CURRENCY_SYMBOL} " if symbol else ""
    return f"{'-' if negative else ''}{prefix}{grouped}"


def _below_hundred(number: int) -> str:
    if number < 20:
        return _UNITS[number]
    tens, units = divmod(number, 10)
    return f"{_TENS[tens]}-{_UNITS[units]}" if units else _TENS[tens]


def number_in_words_en(number: int) -> str:
    """Whole numbers in words, using lakh and crore."""
    if number < 0:
        return f"minus {number_in_words_en(-number)}"
    if number < 100:
        return _below_hundred(number)
    if number < 1_000:
        hundreds, rest = divmod(number, 100)
        words = f"{_UNITS[hundreds]} hundred"
        return f"{words} {number_in_words_en(rest)}" if rest else words
    if number < LAKH:
        thousands, rest = divmod(number, 1_000)
        words = f"{number_in_words_en(thousands)} thousand"
        return f"{words} {number_in_words_en(rest)}" if rest else words
    if number < CRORE:
        lakhs, rest = divmod(number, LAKH)
        words = f"{number_in_words_en(lakhs)} lakh"
        return f"{words} {number_in_words_en(rest)}" if rest else words
    crores, rest = divmod(number, CRORE)
    words = f"{number_in_words_en(crores)} crore"
    return f"{words} {number_in_words_en(rest)}" if rest else words


def amount_in_words_en(amount: Decimal | int | str) -> str:
    """The total in words for a tax invoice.

    `123456.50` becomes `One lakh twenty-three thousand four hundred fifty-six rupees and
    fifty paisa only`.
    """
    value = quantize_money(amount)
    negative = value < 0
    rupees, paisa = divmod(int(abs(value) * 100), 100)

    words = f"{number_in_words_en(rupees)} rupees"
    if paisa:
        words += f" and {number_in_words_en(paisa)} paisa"
    words += " only"
    if negative:
        words = f"minus {words}"
    return words[0].upper() + words[1:]
