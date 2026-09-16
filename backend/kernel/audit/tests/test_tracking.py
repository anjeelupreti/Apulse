"""Every change to a tracked model leaves an entry, whether anybody remembered to log it or not."""

import pytest

from kernel.audit import tracking
from kernel.audit.context import audit_context
from kernel.audit.models import AuditAction, AuditEvent
from kernel.audit.services import verify_chain
from kernel.identity.models import User
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Branch, Location, LocationType
from kernel.tenancy.tests.factories import make_tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return make_tenant("alpha")


@pytest.fixture
def inside(tenant):
    with tenant_context(tenant.tenant.id):
        yield


@pytest.fixture
def user():
    return User.objects.create_user("ram@example.com", "password-1234", full_name="Ram Sharma")


def events_for(instance):
    return list(AuditEvent.objects.filter(entity_id=str(instance.pk)).order_by("sequence"))


def a_location(tenant, **overrides):
    """A tracked kernel model, to exercise the mechanism on something the kernel owns."""
    return Location.objects.create(
        branch=tenant.branch,
        code=overrides.pop("code", "SHELF-A"),
        name=overrides.pop("name", "Shelf A"),
        type=LocationType.SHELF,
        **overrides,
    )


# --------------------------------------------------------------------------- the basics
def test_creating_a_tracked_row_is_recorded(inside, tenant):
    shelf = a_location(tenant)

    events = events_for(shelf)
    assert len(events) == 1
    assert events[0].action == AuditAction.CREATE
    assert events[0].changes["name"]["to"] == "Shelf A"


def test_changing_it_records_only_what_changed(inside, tenant):
    shelf = a_location(tenant)
    shelf.name = "Shelf A (top)"
    shelf.save()

    change = events_for(shelf)[-1]
    assert change.action == AuditAction.UPDATE
    assert set(change.changes) == {"name"}
    assert change.changes["name"] == {"from": "Shelf A", "to": "Shelf A (top)"}


def test_a_decimal_that_did_not_move_is_not_reported_as_moved(inside, tenant):
    """In memory a decimal reads `0`; in the column it reads `0.0000`. Comparing the two as
    written would make every save of an untouched row look like a change."""
    branch = Branch.objects.get(pk=tenant.branch.pk)
    before = AuditEvent.objects.count()
    branch.save()

    assert AuditEvent.objects.count() == before


def test_a_save_that_changes_nothing_records_nothing(inside, tenant):
    """`updated_at` moves on every save. Without excluding it, every touch would look like news."""
    shelf = a_location(tenant)
    shelf.save()

    assert len(events_for(shelf)) == 1


def test_deleting_it_is_recorded(inside, tenant):
    shelf = a_location(tenant)
    pk = shelf.pk
    shelf.delete()

    deleted = AuditEvent.objects.filter(entity_id=str(pk)).order_by("sequence").last()
    assert deleted.action == AuditAction.DELETE
    assert deleted.changes["name"]["from"] == "Shelf A"


def test_the_entity_is_named_in_a_way_a_person_can_read(inside, tenant):
    shelf = a_location(tenant)
    event = events_for(shelf)[0]

    assert event.entity_type == "tenancy.Location"
    assert "Shelf A" in event.entity_label


# --------------------------------------------------------------------------- who did it
def test_the_actor_comes_from_the_context_when_nobody_passed_one(inside, tenant, user):
    """A signal handler is handed a model and nothing else. It should still name a person."""
    with audit_context(actor=user):
        shelf = a_location(tenant)

    assert events_for(shelf)[0].actor == user


def test_an_anonymous_caller_is_recorded_as_nobody_rather_than_guessed(inside, tenant):
    class Anonymous:
        is_authenticated = False

    with audit_context(actor=Anonymous()):
        shelf = a_location(tenant)

    assert events_for(shelf)[0].actor is None


# --------------------------------------------------------------------------- the boundaries
def test_a_write_with_no_tenant_bound_is_skipped_rather_than_crashing():
    """The trail is a chain per tenant. A migration, or a command touching platform data, has no
    chain to append to, and must not fall over trying."""
    assert tracking._should_record(False) is False


def test_pausing_stops_the_row_level_entry(inside, tenant):
    """Used where a service records the same save in better words."""
    with tracking.paused():
        shelf = a_location(tenant)

    assert events_for(shelf) == []


def test_pausing_only_lasts_for_the_block(inside, tenant):
    with tracking.paused():
        a_location(tenant, code="QUIET", name="Quiet")
    loud = a_location(tenant, code="LOUD", name="Loud")

    assert len(events_for(loud)) == 1


def test_the_trail_itself_is_not_tracked():
    """It would be a loop, and the table refuses writes it did not make anyway."""
    assert not tracking.is_tracked(AuditEvent)


# --------------------------------------------------------------------------- still evidence
def test_automatic_entries_keep_the_chain_verifiable(inside, tenant):
    """The point of the chain is that it is checkable. Adding entries must not weaken that."""
    for index in range(5):
        a_location(tenant, code=f"SHELF-{index}", name=f"Shelf {index}")

    assert verify_chain().is_intact


def test_a_secret_is_recorded_as_changed_but_never_printed(inside, user):
    """The useful fact is that it changed at 14:02, never what it changed to."""
    from kernel.audit.diffing import comparable
    from kernel.audit.services import record_update

    before = comparable(user)
    user.password = "a-new-hash"
    event = record_update(user, before)

    assert event.changes["password"] == {"from": "***", "to": "***"}
