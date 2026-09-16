"""Number series and the ranges leased to offline devices."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.tenancy.models import TenantScopedModel


class NumberSeries(TenantScopedModel):
    """One counter: a branch's numbers for one document type in one fiscal year.

    Once a number has been issued the pattern and the counter are frozen. Renumbering after the
    fact would break the one promise a tax invoice number makes — that it identifies exactly one
    document, permanently.
    """

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    document_type = models.CharField(max_length=60)
    fiscal_year = models.CharField(max_length=9, help_text="As written on documents: 2082/83")
    pattern = models.CharField(max_length=100)
    next_number = models.PositiveIntegerField(default=1)
    #: Set the first time a number is issued; the series is immutable from then on.
    first_issued_at = models.DateTimeField(null=True, blank=True)
    last_issued_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "number series"
        ordering = ["branch", "document_type", "fiscal_year"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "branch", "document_type", "fiscal_year"],
                name="numbering_one_series_per_branch_year",
            )
        ]

    def __str__(self) -> str:
        return f"{self.document_type} {self.fiscal_year} @ {self.branch_id}"

    @property
    def has_been_used(self) -> bool:
        return self.first_issued_at is not None


class NumberRange(TenantScopedModel):
    """A block of numbers handed to one device so it can bill while offline.

    A device that cannot reach the server still has to give the customer a bill, so it is lent
    numbers in advance. The cost is that a branch's numbers are no longer strictly contiguous if a
    block is only partly used — see CR-IRD-06, which asks IRD whether that is acceptable.
    """

    series = models.ForeignKey(NumberSeries, on_delete=models.PROTECT, related_name="ranges")
    device_id = models.CharField(max_length=64)
    start_number = models.PositiveIntegerField()
    end_number = models.PositiveIntegerField()
    #: The next number the device will use. Reported back when it syncs.
    next_number = models.PositiveIntegerField()
    released_at = models.DateTimeField(
        null=True, blank=True, help_text="When the device gave the rest of the block back."
    )

    class Meta:
        ordering = ["series", "start_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "series", "start_number"],
                name="numbering_unique_range_start",
            ),
            models.CheckConstraint(
                condition=models.Q(end_number__gte=models.F("start_number")),
                name="numbering_range_is_not_backwards",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.start_number}-{self.end_number} on {self.device_id}"

    @property
    def size(self) -> int:
        return self.end_number - self.start_number + 1

    @property
    def used(self) -> int:
        return self.next_number - self.start_number

    @property
    def remaining(self) -> int:
        return self.end_number - self.next_number + 1

    @property
    def is_exhausted(self) -> bool:
        return self.next_number > self.end_number

    @property
    def is_running_low(self) -> bool:
        """Time to lease another block. Refilled early so a device never runs out mid-shift."""
        return self.remaining <= max(1, self.size // 5)


class SeriesLockedError(RuntimeError):
    """Someone tried to change a series that has already issued numbers."""


class RangeExhaustedError(RuntimeError):
    """A device used every number it was lent and has not been given more."""


class NumberingChoices(models.TextChoices):
    """Reasons a range was given back, kept for the audit trail."""

    SYNCED = "synced", _("Returned after syncing")
    DEVICE_RETIRED = "device_retired", _("Device retired")
    YEAR_ENDED = "year_ended", _("Fiscal year ended")
