"""The `calendar` and `no_calendar` fixtures live in the root conftest, for every suite to use."""

from shared.nepali_calendar.testing import (
    SYNTHETIC_EPOCH_DATE,
    SYNTHETIC_EPOCH_YEAR,
    SYNTHETIC_MONTHS,
)

__all__ = ("SYNTHETIC_EPOCH_DATE", "SYNTHETIC_EPOCH_YEAR", "SYNTHETIC_MONTHS")
