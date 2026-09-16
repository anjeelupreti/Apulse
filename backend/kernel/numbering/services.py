"""Issuing document numbers, and lending blocks of them to offline devices."""

from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import structlog
from django.db import transaction
from django.utils import timezone

from kernel.audit import services as audit
from kernel.audit.models import AuditAction
from shared.nepali_calendar import fiscal_year_for_ad, fiscal_year_from_label

from . import registry
from .models import (
    NumberRange,
    NumberSeries,
    RangeExhaustedError,
    SeriesLockedError,
)

logger = structlog.get_logger(__name__)

#: Leased blocks are refilled well before they run out, so a counter never stalls mid-shift.
DEFAULT_RANGE_SIZE = 500


@dataclass(frozen=True, slots=True)
class IssuedNumber:
    number: str
    sequence: int
    fiscal_year: str
    series_id: Any
    device_id: str = ""

    def __str__(self) -> str:
        return self.number


def _fiscal_year_label(on_date: date | None, fiscal_year: str | None) -> str:
    if fiscal_year:
        return fiscal_year_from_label(fiscal_year).label
    return fiscal_year_for_ad(on_date or timezone.localdate()).label


def _render(series: NumberSeries, sequence: int, branch_code: str) -> str:
    document_type = registry.get(series.document_type)
    return registry.render(
        series.pattern,
        sequence=sequence,
        abbreviation=document_type.abbreviation,
        branch_code=branch_code,
        fiscal_year=series.fiscal_year,
        bs_year=series.fiscal_year.split("/")[0],
    )


@transaction.atomic
def get_or_create_series(
    *,
    document_type: str,
    branch: Any,
    on_date: date | None = None,
    fiscal_year: str | None = None,
) -> NumberSeries:
    """The counter for this branch, document type and fiscal year, creating it if needed.

    A new fiscal year gets a fresh series automatically, starting at 1 — which is what Nepal's
    numbering rules require on Shrawan 1.
    """
    definition = registry.get(document_type)
    label = _fiscal_year_label(on_date, fiscal_year)

    series, created = cast(
        "tuple[NumberSeries, bool]",
        NumberSeries.objects.get_or_create(
            branch=branch,
            document_type=document_type,
            fiscal_year=label,
            defaults={"pattern": definition.pattern},
        ),
    )
    if created:
        logger.info(
            "number_series_created",
            document_type=document_type,
            fiscal_year=label,
            branch_id=str(branch.pk),
        )
        audit.record(
            action=AuditAction.SETTINGS_CHANGE,
            entity=series,
            entity_label=f"{definition.name_en} numbering for {label}",
            changes={"pattern": {"from": None, "to": series.pattern}},
            reason="Fiscal year numbering opened",
            branch=branch,
        )
    return series


@transaction.atomic
def issue_number(
    *,
    document_type: str,
    branch: Any,
    on_date: date | None = None,
    fiscal_year: str | None = None,
) -> IssuedNumber:
    """Take the next number for a document.

    Call this when a document is *posted*, never when a draft is opened. A number taken for a
    draft that is then abandoned leaves a gap, and a gap in an invoice series is what an IRD
    inspection asks about.
    """
    series = get_or_create_series(
        document_type=document_type, branch=branch, on_date=on_date, fiscal_year=fiscal_year
    )
    # Locked for the rest of the transaction: two counters billing at once must not be handed
    # the same number.
    locked = cast("NumberSeries", NumberSeries.objects.select_for_update().get(pk=series.pk))
    if not locked.is_active:
        raise SeriesLockedError(f"Numbering for {document_type} in {locked.fiscal_year} is closed.")

    sequence = locked.next_number
    now = timezone.now()
    locked.next_number = sequence + 1
    locked.last_issued_at = now
    if locked.first_issued_at is None:
        locked.first_issued_at = now
    locked.save(update_fields=["next_number", "first_issued_at", "last_issued_at", "updated_at"])

    return IssuedNumber(
        number=_render(locked, sequence, branch.code),
        sequence=sequence,
        fiscal_year=locked.fiscal_year,
        series_id=locked.pk,
    )


def preview_next(
    *,
    document_type: str,
    branch: Any,
    on_date: date | None = None,
    fiscal_year: str | None = None,
) -> str:
    """What the next number would look like, without taking it."""
    definition = registry.get(document_type)
    label = _fiscal_year_label(on_date, fiscal_year)
    series = NumberSeries.objects.filter(
        branch=branch, document_type=document_type, fiscal_year=label
    ).first()

    if series is None:
        return registry.render(
            definition.pattern,
            sequence=1,
            abbreviation=definition.abbreviation,
            branch_code=branch.code,
            fiscal_year=label,
            bs_year=label.split("/")[0],
        )
    return _render(series, series.next_number, branch.code)


@transaction.atomic
def set_pattern(series: NumberSeries, pattern: str) -> NumberSeries:
    """Change the format of a series that has not issued anything yet."""
    if series.has_been_used:
        raise SeriesLockedError(
            f"{series.document_type} for {series.fiscal_year} has already issued numbers, so its "
            "format cannot change. Documents already carry the old format."
        )
    registry.validate_pattern(pattern)
    series.pattern = pattern
    series.save(update_fields=["pattern", "updated_at"])
    return series


@transaction.atomic
def set_next_number(series: NumberSeries, next_number: int) -> NumberSeries:
    """Set the starting number, for a pharmacy continuing a series from its old system."""
    if series.has_been_used:
        raise SeriesLockedError(
            f"{series.document_type} for {series.fiscal_year} has already issued numbers. "
            "Resetting the counter would reuse numbers that documents already carry."
        )
    if next_number < 1:
        raise ValueError("Numbering starts at 1.")
    series.next_number = next_number
    series.save(update_fields=["next_number", "updated_at"])
    return series


# --------------------------------------------------------------------------- offline devices
@transaction.atomic
def lease_range(
    *,
    document_type: str,
    branch: Any,
    device_id: str,
    size: int = DEFAULT_RANGE_SIZE,
    on_date: date | None = None,
    fiscal_year: str | None = None,
) -> NumberRange:
    """Lend a device a block of numbers to use while it has no connection.

    The series counter jumps past the block, so numbers issued on the server can never collide
    with numbers the device is holding.
    """
    if size < 1:
        raise ValueError("A leased block needs at least one number.")

    series = get_or_create_series(
        document_type=document_type, branch=branch, on_date=on_date, fiscal_year=fiscal_year
    )
    locked = cast("NumberSeries", NumberSeries.objects.select_for_update().get(pk=series.pk))

    start = locked.next_number
    end = start + size - 1
    locked.next_number = end + 1
    if locked.first_issued_at is None:
        locked.first_issued_at = timezone.now()
    locked.save(update_fields=["next_number", "first_issued_at", "updated_at"])

    leased = cast(
        "NumberRange",
        NumberRange.objects.create(
            series=locked,
            device_id=device_id,
            start_number=start,
            end_number=end,
            next_number=start,
        ),
    )
    logger.info(
        "number_range_leased",
        document_type=document_type,
        device_id=device_id,
        start=start,
        end=end,
    )
    audit.record(
        action=AuditAction.SETTINGS_CHANGE,
        entity=leased,
        entity_label=f"{document_type} numbers {start}-{end} to device {device_id}",
        changes={"range": {"from": None, "to": f"{start}-{end}"}},
        reason="Numbers lent for offline billing",
        branch=branch,
    )
    return leased


def take_from_range(leased: NumberRange, branch_code: str) -> IssuedNumber:
    """Take the next number from a leased block.

    This is what a device does locally. The server runs the same code when replaying a device's
    documents, so both sides produce identical numbers.
    """
    if leased.released_at is not None:
        raise RangeExhaustedError("This block has been given back.")
    if leased.is_exhausted:
        raise RangeExhaustedError(
            f"Device {leased.device_id} has used all of {leased.start_number}-{leased.end_number}."
        )

    sequence = leased.next_number
    leased.next_number = sequence + 1
    leased.save(update_fields=["next_number", "updated_at"])

    return IssuedNumber(
        number=_render(leased.series, sequence, branch_code),
        sequence=sequence,
        fiscal_year=leased.series.fiscal_year,
        series_id=leased.series_id,
        device_id=leased.device_id,
    )


@transaction.atomic
def release_range(leased: NumberRange, *, reason: str = "") -> NumberRange:
    """Give an unused tail back.

    The numbers are not returned to the series: reissuing them would produce two documents with
    the same number months apart. The block is simply closed, and the gap is recorded.
    """
    if leased.released_at is not None:
        return leased

    leased.released_at = timezone.now()
    leased.save(update_fields=["released_at", "updated_at"])

    if leased.remaining > 0:
        logger.info(
            "number_range_released_with_gap",
            device_id=leased.device_id,
            unused=leased.remaining,
            first_unused=leased.next_number,
            last_unused=leased.end_number,
        )
        audit.record(
            action=AuditAction.SETTINGS_CHANGE,
            entity=leased,
            entity_label=f"numbers {leased.next_number}-{leased.end_number} never used",
            changes={"unused_numbers": {"from": None, "to": leased.remaining}},
            reason=reason or "Leased block closed with numbers unused",
        )
    return leased


def ranges_running_low(*, device_id: str = "") -> list[NumberRange]:
    """Blocks that should be topped up before a device is left without numbers."""
    query = NumberRange.objects.filter(released_at__isnull=True).select_related("series")
    if device_id:
        query = query.filter(device_id=device_id)
    return [leased for leased in query if leased.is_running_low]
