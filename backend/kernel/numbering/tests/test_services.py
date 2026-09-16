"""The properties IRD actually inspects: sequential, gapless, never reissued, reset each year."""

from datetime import timedelta

import pytest

from kernel.numbering.models import (
    NumberRange,
    NumberSeries,
    RangeExhaustedError,
    SeriesLockedError,
)
from kernel.numbering.services import (
    DEFAULT_RANGE_SIZE,
    issue_number,
    lease_range,
    preview_next,
    ranges_running_low,
    release_range,
    set_next_number,
    set_pattern,
    take_from_range,
)
from kernel.tenancy.context import tenant_context
from kernel.tenancy.services import create_branch
from kernel.tenancy.tests.factories import make_tenant
from shared.nepali_calendar import BSDate, bs_to_ad

from .conftest import CREDIT_NOTE, INVOICE

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("calendar", "document_types")]


@pytest.fixture
def provisioned():
    return make_tenant("alpha")


@pytest.fixture
def branch(provisioned):
    return provisioned.branch


# --------------------------------------------------------------------------- issuing
def test_numbers_start_at_one_and_carry_the_branch_and_year(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        issued = issue_number(
            document_type=INVOICE, branch=branch, on_date=bs_to_ad(BSDate(2071, 4, 1))
        )
    assert issued.sequence == 1
    assert issued.fiscal_year == "2071/72"
    assert issued.number == f"INV-{branch.code}-2071/72-000001"


def test_numbers_run_in_sequence_without_gaps(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        issued = [
            issue_number(document_type=INVOICE, branch=branch, on_date=bs_to_ad(BSDate(2071, 4, 1)))
            for _ in range(25)
        ]
    assert [item.sequence for item in issued] == list(range(1, 26))
    assert len({item.number for item in issued}) == 25


def test_each_document_type_has_its_own_run(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        on_date = bs_to_ad(BSDate(2071, 4, 1))
        invoice = issue_number(document_type=INVOICE, branch=branch, on_date=on_date)
        credit_note = issue_number(document_type=CREDIT_NOTE, branch=branch, on_date=on_date)
    assert invoice.sequence == credit_note.sequence == 1
    assert credit_note.number.startswith("CN-")


def test_each_branch_has_its_own_run(provisioned):
    with tenant_context(provisioned.tenant.id):
        second = create_branch(
            legal_entity=provisioned.legal_entity, code="BR2", name="Second branch"
        )
        on_date = bs_to_ad(BSDate(2071, 4, 1))
        first_branch = issue_number(
            document_type=INVOICE, branch=provisioned.branch, on_date=on_date
        )
        second_branch = issue_number(document_type=INVOICE, branch=second, on_date=on_date)

    assert first_branch.sequence == second_branch.sequence == 1
    assert first_branch.number != second_branch.number


# --------------------------------------------------------------------------- fiscal year
def test_the_run_restarts_on_the_first_of_shrawan(provisioned, branch):
    """Nepal's numbering restarts with the fiscal year, not the Gregorian one."""
    with tenant_context(provisioned.tenant.id):
        last_year = bs_to_ad(BSDate(2072, 3, 1))  # Ashadh, the final month
        for _ in range(5):
            issue_number(document_type=INVOICE, branch=branch, on_date=last_year)

        new_year = bs_to_ad(BSDate(2072, 4, 1))  # Shrawan 1
        first_of_new_year = issue_number(document_type=INVOICE, branch=branch, on_date=new_year)

    assert first_of_new_year.sequence == 1
    assert first_of_new_year.fiscal_year == "2072/73"


def test_a_document_dated_in_the_old_year_still_uses_the_old_run(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        ashadh_end = bs_to_ad(BSDate(2072, 3, 1))
        issue_number(document_type=INVOICE, branch=branch, on_date=ashadh_end)
        issue_number(document_type=INVOICE, branch=branch, on_date=bs_to_ad(BSDate(2072, 4, 1)))
        backdated = issue_number(document_type=INVOICE, branch=branch, on_date=ashadh_end)

    assert backdated.fiscal_year == "2071/72"
    assert backdated.sequence == 2


def test_a_fiscal_year_can_be_named_directly(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        issued = issue_number(document_type=INVOICE, branch=branch, fiscal_year="2075/76")
    assert issued.fiscal_year == "2075/76"


# --------------------------------------------------------------------------- preview
def test_preview_shows_the_next_number_without_taking_it(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        on_date = bs_to_ad(BSDate(2071, 4, 1))
        first_preview = preview_next(document_type=INVOICE, branch=branch, on_date=on_date)
        assert first_preview.endswith("000001")
        assert preview_next(document_type=INVOICE, branch=branch, on_date=on_date) == first_preview

        issued = issue_number(document_type=INVOICE, branch=branch, on_date=on_date)
        assert issued.number == first_preview
        assert preview_next(document_type=INVOICE, branch=branch, on_date=on_date).endswith(
            "000002"
        )


# --------------------------------------------------------------------------- immutability
def test_the_format_cannot_change_once_documents_carry_it(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        issue_number(document_type=INVOICE, branch=branch, on_date=bs_to_ad(BSDate(2071, 4, 1)))
        series = NumberSeries.objects.get(document_type=INVOICE)
        with pytest.raises(SeriesLockedError, match="already issued"):
            set_pattern(series, "{TYPE}/{SEQ:4}")


def test_the_counter_cannot_be_reset_once_used(provisioned, branch):
    """Resetting would hand out numbers that documents already carry."""
    with tenant_context(provisioned.tenant.id):
        issue_number(document_type=INVOICE, branch=branch, on_date=bs_to_ad(BSDate(2071, 4, 1)))
        series = NumberSeries.objects.get(document_type=INVOICE)
        with pytest.raises(SeriesLockedError, match="already issued"):
            set_next_number(series, 1)


def test_an_unused_series_can_be_set_up_first(provisioned, branch):
    """A pharmacy moving from another system continues its old run."""
    with tenant_context(provisioned.tenant.id):
        preview_next(document_type=INVOICE, branch=branch, on_date=bs_to_ad(BSDate(2071, 4, 1)))
        series = NumberSeries.objects.create(
            branch=branch,
            document_type=INVOICE,
            fiscal_year="2071/72",
            pattern="{TYPE}-{SEQ:5}",
        )
        set_next_number(series, 4501)
        issued = issue_number(
            document_type=INVOICE, branch=branch, on_date=bs_to_ad(BSDate(2071, 4, 1))
        )
    assert issued.number == "INV-04501"


def test_a_closed_series_issues_nothing(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        issue_number(document_type=INVOICE, branch=branch, on_date=bs_to_ad(BSDate(2071, 4, 1)))
        series = NumberSeries.objects.get(document_type=INVOICE)
        series.is_active = False
        series.save(update_fields=["is_active"])

        with pytest.raises(SeriesLockedError, match="closed"):
            issue_number(document_type=INVOICE, branch=branch, on_date=bs_to_ad(BSDate(2071, 4, 1)))


# --------------------------------------------------------------------------- offline devices
def test_a_device_is_lent_a_block_and_the_server_skips_past_it(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        on_date = bs_to_ad(BSDate(2071, 4, 1))
        leased = lease_range(
            document_type=INVOICE, branch=branch, device_id="counter-1", size=100, on_date=on_date
        )
        assert (leased.start_number, leased.end_number) == (1, 100)

        # A number issued on the server must not collide with the lent block.
        on_server = issue_number(document_type=INVOICE, branch=branch, on_date=on_date)
    assert on_server.sequence == 101


def test_two_devices_get_separate_blocks(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        on_date = bs_to_ad(BSDate(2071, 4, 1))
        first = lease_range(
            document_type=INVOICE, branch=branch, device_id="counter-1", size=50, on_date=on_date
        )
        second = lease_range(
            document_type=INVOICE, branch=branch, device_id="counter-2", size=50, on_date=on_date
        )
    assert (first.start_number, first.end_number) == (1, 50)
    assert (second.start_number, second.end_number) == (51, 100)


def test_a_device_bills_from_its_block(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        leased = lease_range(
            document_type=INVOICE,
            branch=branch,
            device_id="counter-1",
            size=3,
            on_date=bs_to_ad(BSDate(2071, 4, 1)),
        )
        numbers = [take_from_range(leased, branch.code) for _ in range(3)]

    assert [item.sequence for item in numbers] == [1, 2, 3]
    assert all(item.device_id == "counter-1" for item in numbers)
    assert numbers[0].number == f"INV-{branch.code}-2071/72-000001"


def test_a_device_that_runs_out_is_told_so_rather_than_reusing_numbers(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        leased = lease_range(
            document_type=INVOICE,
            branch=branch,
            device_id="counter-1",
            size=2,
            on_date=bs_to_ad(BSDate(2071, 4, 1)),
        )
        take_from_range(leased, branch.code)
        take_from_range(leased, branch.code)
        with pytest.raises(RangeExhaustedError, match="used all of"):
            take_from_range(leased, branch.code)


def test_a_block_running_low_is_flagged_before_it_runs_out(provisioned, branch):
    """A counter must never stall mid-shift waiting for numbers."""
    with tenant_context(provisioned.tenant.id):
        leased = lease_range(
            document_type=INVOICE,
            branch=branch,
            device_id="counter-1",
            size=10,
            on_date=bs_to_ad(BSDate(2071, 4, 1)),
        )
        assert not leased.is_running_low
        for _ in range(8):
            take_from_range(leased, branch.code)
        assert leased.is_running_low
        assert [item.pk for item in ranges_running_low()] == [leased.pk]


def test_giving_a_block_back_records_the_numbers_that_were_never_used(provisioned, branch):
    """The unused numbers are not recycled: two documents must never share a number."""
    from kernel.audit.models import AuditEvent

    with tenant_context(provisioned.tenant.id):
        on_date = bs_to_ad(BSDate(2071, 4, 1))
        leased = lease_range(
            document_type=INVOICE, branch=branch, device_id="counter-1", size=10, on_date=on_date
        )
        take_from_range(leased, branch.code)
        release_range(leased, reason="Device retired")

        assert leased.released_at is not None
        with pytest.raises(RangeExhaustedError, match="given back"):
            take_from_range(leased, branch.code)

        # The next server-issued number continues past the whole block, gap and all.
        assert issue_number(document_type=INVOICE, branch=branch, on_date=on_date).sequence == 11
        assert AuditEvent.objects.filter(entity_label__contains="never used").exists()


def test_releasing_twice_is_harmless(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        leased = lease_range(
            document_type=INVOICE,
            branch=branch,
            device_id="counter-1",
            size=5,
            on_date=bs_to_ad(BSDate(2071, 4, 1)),
        )
        first = release_range(leased)
        assert release_range(leased).released_at == first.released_at


def test_the_default_block_is_big_enough_for_a_day_of_billing(provisioned, branch):
    with tenant_context(provisioned.tenant.id):
        leased = lease_range(
            document_type=INVOICE,
            branch=branch,
            device_id="counter-1",
            on_date=bs_to_ad(BSDate(2071, 4, 1)),
        )
    assert leased.size == DEFAULT_RANGE_SIZE


def test_an_empty_block_is_refused(provisioned, branch):
    with tenant_context(provisioned.tenant.id), pytest.raises(ValueError, match="at least one"):
        lease_range(
            document_type=INVOICE,
            branch=branch,
            device_id="counter-1",
            size=0,
            on_date=bs_to_ad(BSDate(2071, 4, 1)),
        )


# --------------------------------------------------------------------------- isolation
def test_numbering_does_not_leak_between_pharmacies(branch):
    first = make_tenant("alpha")
    second = make_tenant("bravo")
    on_date = bs_to_ad(BSDate(2071, 4, 1))

    with tenant_context(first.tenant.id):
        issue_number(document_type=INVOICE, branch=first.branch, on_date=on_date)
        issue_number(document_type=INVOICE, branch=first.branch, on_date=on_date)

    with tenant_context(second.tenant.id):
        issued = issue_number(document_type=INVOICE, branch=second.branch, on_date=on_date)
        assert issued.sequence == 1
        assert NumberSeries.objects.count() == 1
        assert NumberRange.objects.count() == 0


def test_opening_a_series_is_recorded(provisioned, branch):
    from kernel.audit.models import AuditEvent

    with tenant_context(provisioned.tenant.id):
        issue_number(document_type=INVOICE, branch=branch, on_date=bs_to_ad(BSDate(2071, 4, 1)))
        assert AuditEvent.objects.filter(entity_label__contains="numbering for 2071/72").exists()


def test_without_a_calendar_a_dated_document_cannot_be_numbered(provisioned, branch, no_calendar):
    """Guessing a fiscal year would put the document in the wrong year's run."""
    from shared.nepali_calendar import CalendarNotLoadedError

    with tenant_context(provisioned.tenant.id), pytest.raises(CalendarNotLoadedError):
        issue_number(document_type=INVOICE, branch=branch)


def test_a_named_fiscal_year_still_needs_the_calendar(provisioned, branch, no_calendar):
    from shared.nepali_calendar import CalendarNotLoadedError

    with tenant_context(provisioned.tenant.id), pytest.raises(CalendarNotLoadedError):
        issue_number(document_type=INVOICE, branch=branch, fiscal_year="2082/83")


def test_dates_near_the_year_boundary_land_in_the_right_run(provisioned, branch, calendar):
    with tenant_context(provisioned.tenant.id):
        # Derived from the table: Ashadh is not always the same length.
        last_of_ashadh = calendar.days_in_month(2072, 3)
        last_day_of_ashadh = bs_to_ad(BSDate(2072, 3, last_of_ashadh))
        before = issue_number(document_type=INVOICE, branch=branch, on_date=last_day_of_ashadh)
        after = issue_number(
            document_type=INVOICE, branch=branch, on_date=last_day_of_ashadh + timedelta(days=1)
        )
    assert before.fiscal_year == "2071/72"
    assert after.fiscal_year == "2072/73"
    assert after.sequence == 1
