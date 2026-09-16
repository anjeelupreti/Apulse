"""The narrowest scope that has a value wins, and nothing set means the declared default."""

from decimal import Decimal

import pytest

from kernel.identity.models import User
from kernel.settings import services as settings
from kernel.settings.models import SettingValue
from kernel.settings.registry import Scope, SettingValueError
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Branch
from kernel.tenancy.tests.factories import make_tenant

pytestmark = pytest.mark.django_db

KEY = "payments.over_limit_behaviour"
GRACE = "payments.overdue_grace_days"


@pytest.fixture
def provisioned():
    return make_tenant("alpha")


@pytest.fixture
def inside(provisioned):
    with tenant_context(provisioned.tenant.id):
        yield


@pytest.fixture
def branch(provisioned):
    return provisioned.branch


@pytest.fixture
def other_branch(provisioned):
    return Branch.objects.create(
        legal_entity=provisioned.legal_entity, code="BR2", name="Second branch"
    )


@pytest.fixture
def user():
    return User.objects.create_user("ram@example.com", "password-1234", full_name="Ram Sharma")


# --------------------------------------------------------------------------- the default
def test_nothing_set_anywhere_means_the_declared_default(inside):
    assert settings.get(KEY) == "block"


def test_the_default_is_where_it_came_from(inside):
    resolved = settings.resolve(KEY)
    assert resolved.is_default
    assert resolved.scope is None


def test_an_undeclared_key_raises_rather_than_shrugging(inside):
    from kernel.settings.registry import UnknownSettingError

    with pytest.raises(UnknownSettingError):
        settings.get("payments.no_such_thing")


# --------------------------------------------------------------------------- narrowest wins
def test_a_value_for_the_account_applies_everywhere_in_it(inside, branch):
    settings.set_value(KEY, "warn")
    assert settings.get(KEY) == "warn"
    assert settings.get(KEY, branch=branch) == "warn"


def test_a_branch_value_beats_the_account_value(inside, branch, other_branch):
    settings.set_value(KEY, "warn")
    settings.set_value(KEY, "block", scope=Scope.BRANCH, branch=branch)

    assert settings.get(KEY, branch=branch) == "block"
    assert settings.get(KEY, branch=other_branch) == "warn"
    assert settings.get(KEY) == "warn"


def test_the_screen_can_say_where_a_value_came_from(inside, branch):
    """ "Inherited from the business" and "set for this branch" are different to the person."""
    settings.set_value(KEY, "warn")
    assert settings.resolve(KEY, branch=branch).scope is Scope.TENANT

    settings.set_value(KEY, "block", scope=Scope.BRANCH, branch=branch)
    assert settings.resolve(KEY, branch=branch).scope is Scope.BRANCH


def test_a_legal_entity_value_sits_between_the_two(inside, branch, provisioned):
    settings.set_value(KEY, "warn")
    settings.set_value(
        KEY, "block", scope=Scope.LEGAL_ENTITY, legal_entity=provisioned.legal_entity
    )

    assert settings.get(KEY, branch=branch) == "block"
    assert settings.get(KEY) == "warn"


def test_a_branch_knows_its_own_business_without_being_told(inside, branch, provisioned):
    """The caller passes the branch; the legal entity is looked up from it."""
    settings.set_value(KEY, "warn", scope=Scope.LEGAL_ENTITY, legal_entity=provisioned.legal_entity)
    assert settings.get(KEY, branch=branch) == "warn"


def test_clearing_a_value_lets_the_wider_one_apply_again(inside, branch):
    settings.set_value(KEY, "warn")
    settings.set_value(KEY, "block", scope=Scope.BRANCH, branch=branch)
    assert settings.get(KEY, branch=branch) == "block"

    settings.clear(KEY, scope=Scope.BRANCH, branch=branch)
    assert settings.get(KEY, branch=branch) == "warn"


def test_clearing_everything_goes_back_to_the_declared_default(inside):
    settings.set_value(KEY, "warn")
    settings.clear(KEY)
    assert settings.get(KEY) == "block"


# --------------------------------------------------------------------------- what is refused
def test_a_value_the_setting_does_not_accept_is_refused(inside):
    with pytest.raises(SettingValueError, match="must be one of"):
        settings.set_value(KEY, "ignore")


def test_a_setting_cannot_be_set_at_a_scope_it_does_not_allow(inside, user):
    with pytest.raises(SettingValueError, match="cannot be set per"):
        settings.set_value(KEY, "warn", scope=Scope.USER, user=user)


def test_a_narrow_scope_has_to_say_which_one(inside):
    with pytest.raises(SettingValueError, match="needs to say which one"):
        settings.set_value(KEY, "warn", scope=Scope.BRANCH)


def test_the_platform_default_is_the_code_default_not_a_row(inside):
    """A tenant-less row cannot be protected by row-level security. The default is in code."""
    with pytest.raises(SettingValueError, match="control plane"):
        settings.set_value(KEY, "warn", scope=Scope.PLATFORM)


def test_a_stored_value_that_is_no_longer_valid_falls_back(inside, branch):
    """A choice removed in a release must not take the counter down with it."""
    settings.set_value(KEY, "warn")
    SettingValue.objects.filter(key=KEY).update(value="ignore")
    settings.invalidate(branch.tenant_id)

    assert settings.get(KEY) == "block"


# --------------------------------------------------------------------------- isolation and trail
def test_one_account_cannot_see_another_accounts_settings(inside, provisioned):
    settings.set_value(KEY, "warn")
    bravo = make_tenant("bravo")

    with tenant_context(bravo.tenant.id):
        assert settings.get(KEY) == "block"


def test_with_no_account_bound_everything_is_the_default(provisioned):
    settings.set_value(KEY, "warn", tenant_id=provisioned.tenant.id)
    assert settings.get(KEY) == "block"


def test_changing_a_setting_is_recorded_with_its_reason(inside, user):
    from kernel.audit.models import AuditAction, AuditEvent

    settings.set_value(GRACE, 5, actor=user, reason="Agreed with the hospital")

    event = (
        AuditEvent.objects.filter(action=AuditAction.SETTINGS_CHANGE).order_by("-sequence").first()
    )
    assert event.changes[GRACE] == {"from": None, "to": "5"}
    assert event.reason == "Agreed with the hospital"
    assert event.actor == user


def test_the_trail_shows_what_it_changed_from(inside):
    from kernel.audit.models import AuditAction, AuditEvent

    settings.set_value(GRACE, 5)
    settings.set_value(GRACE, 10)

    event = (
        AuditEvent.objects.filter(action=AuditAction.SETTINGS_CHANGE).order_by("-sequence").first()
    )
    assert event.changes[GRACE] == {"from": "5", "to": "10"}


def test_clearing_is_recorded_too(inside):
    from kernel.audit.models import AuditAction, AuditEvent

    settings.set_value(GRACE, 5)
    settings.clear(GRACE, reason="Back to the standard terms")

    event = (
        AuditEvent.objects.filter(action=AuditAction.SETTINGS_CHANGE).order_by("-sequence").first()
    )
    assert "inherited" in event.changes[GRACE]["to"]


# --------------------------------------------------------------------------- typed readers
def test_typed_readers_hand_back_real_types(inside):
    settings.set_value(GRACE, "7")
    assert settings.get_int(GRACE) == 7
    assert settings.get_decimal("payments.till_variance_tolerance") == Decimal("1.00")
    assert settings.get_bool("payments.require_witness_for_cash_out") is True
    assert settings.get_str(KEY) == "block"


def test_everything_for_a_module_reads_in_one_go(inside):
    values = settings.effective("payments")
    assert values["payments.over_limit_behaviour"] == "block"
    assert values["payments.overdue_grace_days"] == 0
