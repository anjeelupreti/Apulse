"""Month names. The BS year begins in Baisakh; the fiscal year begins in Shrawan."""

MONTH_NAMES_EN: tuple[str, ...] = (
    "Baisakh",
    "Jestha",
    "Ashadh",
    "Shrawan",
    "Bhadra",
    "Ashwin",
    "Kartik",
    "Mangsir",
    "Poush",
    "Magh",
    "Falgun",
    "Chaitra",
)

MONTH_NAMES_NE: tuple[str, ...] = (
    "बैशाख",
    "जेठ",
    "असार",
    "साउन",
    "भदौ",
    "असोज",
    "कार्तिक",
    "मंसिर",
    "पुष",
    "माघ",
    "फागुन",
    "चैत",
)

#: Shrawan, the fourth month, starts Nepal's fiscal year.
FISCAL_YEAR_START_MONTH = 4


def month_name(month: int, language: str = "en") -> str:
    if not 1 <= month <= 12:
        raise ValueError(f"Month must be 1-12, got {month}")
    names = MONTH_NAMES_NE if language.startswith("ne") else MONTH_NAMES_EN
    return names[month - 1]
