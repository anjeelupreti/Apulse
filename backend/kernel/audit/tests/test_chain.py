"""The properties that make the trail evidence rather than a convenience."""

import pytest
from django.db import DatabaseError, connection, transaction

from kernel.audit.diffing import comparable
from kernel.audit.models import GENESIS_HASH, AuditAction, AuditChainHead, AuditEvent
from kernel.audit.services import (
    compute_hash,
    history_for,
    record,
    record_create,
    record_update,
    verify_chain,
)
from kernel.identity.models import User
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Branch
from kernel.tenancy.tests.factories import make_tenant, make_tenant_only

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    """A bare tenant, with nothing provisioned under it.

    These tests are about the chain itself, so they want to own it. Provisioning a real tenant
    creates a legal entity, a branch and its locations, and all three are tracked — which is the
    point of tracking them, but it means the chain does not start empty.
    """
    return make_tenant_only("alpha")


@pytest.fixture
def provisioned():
    """A complete tenant, for the tests that need something real to change."""
    return make_tenant("bravo")


@pytest.fixture
def user():
    return User.objects.create_user("ram@example.com", "password-1234", full_name="Ram Sharma")


# --------------------------------------------------------------------------- the chain
def test_the_first_entry_starts_from_genesis(tenant, user):
    with tenant_context(tenant.id):
        event = record(action=AuditAction.LOGIN, actor=user)
        assert event.sequence == 1
        assert event.previous_hash == GENESIS_HASH
        assert len(event.hash) == 64


def test_each_entry_links_to_the_one_before(tenant, user):
    with tenant_context(tenant.id):
        first = record(action=AuditAction.LOGIN, actor=user)
        second = record(action=AuditAction.EXPORT, actor=user)
        third = record(action=AuditAction.LOGOUT, actor=user)

    assert [e.sequence for e in (first, second, third)] == [1, 2, 3]
    assert second.previous_hash == first.hash
    assert third.previous_hash == second.hash


def test_the_chain_head_tracks_the_tip(tenant, user):
    with tenant_context(tenant.id):
        record(action=AuditAction.LOGIN, actor=user)
        latest = record(action=AuditAction.LOGOUT, actor=user)
        head = AuditChainHead.objects.get()
    assert head.sequence == latest.sequence
    assert head.last_hash == latest.hash


def test_verification_passes_on_an_untouched_chain(tenant, user):
    with tenant_context(tenant.id):
        for _ in range(5):
            record(action=AuditAction.PRINT, actor=user)
        result = verify_chain()
    assert result.is_intact
    assert result.checked == 5
    assert bool(result) is True


def test_verification_spots_a_forged_entry(tenant, user):
    """Inserts are allowed, so an attacker's realistic move is to add a plausible entry."""
    with tenant_context(tenant.id):
        record(action=AuditAction.LOGIN, actor=user)
        AuditEvent.objects.create(
            sequence=2,
            previous_hash="f" * 64,  # does not follow entry #1
            hash="e" * 64,
            action=AuditAction.VOID,
            actor=user,
            reason="Never happened",
        )
        result = verify_chain()

    assert not result.is_intact
    assert result.broken_at == 2
    assert "does not follow" in result.problem


def test_verification_spots_contents_that_do_not_match_the_hash(tenant, user):
    with tenant_context(tenant.id):
        genuine = record(action=AuditAction.LOGIN, actor=user)
        AuditEvent.objects.create(
            sequence=2,
            previous_hash=genuine.hash,
            hash="0" * 63 + "1",
            action=AuditAction.OVERRIDE,
            actor=user,
            reason="Tampered",
        )
        result = verify_chain()

    assert not result.is_intact
    assert result.broken_at == 2
    assert "do not match its hash" in result.problem


def test_verification_spots_a_gap(tenant, user):
    with tenant_context(tenant.id):
        first = record(action=AuditAction.LOGIN, actor=user)
        AuditEvent.objects.create(
            sequence=3,  # #2 is missing
            previous_hash=first.hash,
            hash="a" * 64,
            action=AuditAction.LOGOUT,
            actor=user,
        )
        result = verify_chain()

    assert not result.is_intact
    assert "Expected entry #2" in result.problem


def test_hashing_is_stable_regardless_of_key_order():
    first = compute_hash(previous_hash="x", payload={"a": 1, "b": 2})
    second = compute_hash(previous_hash="x", payload={"b": 2, "a": 1})
    assert first == second


# --------------------------------------------------------------------------- append-only
def test_entries_cannot_be_changed(tenant, user):
    with tenant_context(tenant.id):
        event = record(action=AuditAction.VOID, actor=user, reason="Wrong customer")
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).update(reason="Nothing to see here")


def test_entries_cannot_be_deleted(tenant, user):
    with tenant_context(tenant.id):
        event = record(action=AuditAction.LOGIN, actor=user)
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).delete()


def test_the_table_cannot_be_emptied_in_one_statement(tenant):
    """Row triggers do not fire for TRUNCATE, so it gets its own statement-level trigger.

    Nothing is recorded first: an insert in the same transaction would make PostgreSQL refuse the
    TRUNCATE for its own reasons, and this test is about ours.
    """
    with (
        tenant_context(tenant.id),
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("TRUNCATE TABLE audit_auditevent")


# --------------------------------------------------------------------------- recording
def test_creating_a_record_captures_its_opening_values(provisioned, user):
    with tenant_context(provisioned.tenant.id):
        branch = Branch.objects.create(
            legal_entity=provisioned.legal_entity, code="BR2", name="Second branch"
        )
        event = record_create(branch, actor=user)

    assert event.action == AuditAction.CREATE
    assert event.entity_type == "tenancy.Branch"
    assert event.entity_id == str(branch.pk)
    assert event.changes["name"] == {"from": None, "to": "Second branch"}
    assert event.actor_label == "Ram Sharma"


def test_updating_records_only_the_fields_that_changed(provisioned, user):
    with tenant_context(provisioned.tenant.id):
        branch = provisioned.branch
        before = comparable(branch)
        branch.name = "Renamed branch"
        branch.save(update_fields=["name", "updated_at"])
        event = record_update(branch, before, actor=user, reason="Signboard changed")

    assert event is not None
    assert set(event.changes) == {"name", "updated_at"}
    assert event.changes["name"]["to"] == "Renamed branch"
    assert event.reason == "Signboard changed"


def test_a_save_that_changed_nothing_records_nothing(provisioned, user):
    with tenant_context(provisioned.tenant.id):
        before = comparable(provisioned.branch)
        written = AuditEvent.objects.count()
        assert record_update(provisioned.branch, before, actor=user) is None
        assert AuditEvent.objects.count() == written


def test_history_for_a_record_reads_newest_first(provisioned, user):
    with tenant_context(provisioned.tenant.id):
        branch = provisioned.branch
        before = comparable(branch)
        branch.name = "Second name"
        record_update(branch, before, actor=user)
        record(action=AuditAction.PRINT, actor=user, entity=branch)

        history = list(history_for(branch))

    # The branch was also created, and that is an entry too — provisioning is not exempt.
    assert [event.action for event in history[:2]] == [AuditAction.PRINT, AuditAction.UPDATE]
    assert history[-1].action == AuditAction.CREATE


def test_system_actions_may_have_no_actor(tenant):
    with tenant_context(tenant.id):
        event = record(action=AuditAction.SETTINGS_CHANGE, reason="Nightly rule-set update")
    assert event.actor_id is None
    assert event.actor_label == ""


# --------------------------------------------------------------------------- isolation
def test_each_tenant_has_its_own_chain(user):
    alpha = make_tenant_only("alpha")
    bravo = make_tenant_only("bravo")

    with tenant_context(alpha.id):
        record(action=AuditAction.LOGIN, actor=user)
        record(action=AuditAction.LOGOUT, actor=user)
    with tenant_context(bravo.id):
        first_for_bravo = record(action=AuditAction.LOGIN, actor=user)
        assert first_for_bravo.sequence == 1
        assert first_for_bravo.previous_hash == GENESIS_HASH
        assert AuditEvent.objects.count() == 1
        assert verify_chain().is_intact

    with tenant_context(alpha.id):
        assert AuditEvent.objects.count() == 2


def test_recording_without_a_tenant_refuses_rather_than_guessing(user):
    from kernel.tenancy.context import NoActiveTenantError

    with pytest.raises(NoActiveTenantError):
        record(action=AuditAction.LOGIN, actor=user)
