from datetime import timedelta

import pytest
from django.utils import timezone

from kernel.entitlements.flags import BUCKETS, bucket_for, flag_allows
from kernel.entitlements.models import FeatureFlag
from shared.ids import uuid7

CODE = "pharmacy.offline_pos"


def flag(**overrides) -> FeatureFlag:
    return FeatureFlag(feature_code=CODE, **overrides)


def test_a_full_rollout_reaches_everyone():
    assert flag_allows(flag(rollout_percent=100), uuid7())


def test_a_zero_rollout_reaches_nobody():
    assert not flag_allows(flag(rollout_percent=0), uuid7())


def test_a_kill_switch_overrides_everything():
    tenant_id = uuid7()
    assert not flag_allows(
        flag(is_killed=True, rollout_percent=100, allowed_tenants=[str(tenant_id)]), tenant_id
    )


def test_an_account_keeps_the_same_bucket():
    """A rollout that reshuffles on every deploy is an outage, not a rollout."""
    tenant_id = uuid7()
    assert bucket_for(CODE, tenant_id) == bucket_for(CODE, tenant_id)


def test_different_features_bucket_independently():
    tenant_id = uuid7()
    buckets = {bucket_for(f"module.feature{n}", tenant_id) for n in range(20)}
    assert len(buckets) > 1


def test_raising_the_percentage_only_adds_accounts():
    """Anyone who had the feature at 30% must still have it at 60%."""
    tenants = [uuid7() for _ in range(300)]
    at_thirty = {t for t in tenants if flag_allows(flag(rollout_percent=30), t)}
    at_sixty = {t for t in tenants if flag_allows(flag(rollout_percent=60), t)}
    assert at_thirty < at_sixty


def test_the_rollout_is_roughly_the_requested_share():
    tenants = [uuid7() for _ in range(2000)]
    reached = sum(1 for t in tenants if flag_allows(flag(rollout_percent=25), t))
    assert 0.20 < reached / len(tenants) < 0.30


def test_an_allow_list_beats_the_percentage():
    """A pilot pharmacy keeps the feature even while the rollout is at zero."""
    tenant_id = uuid7()
    assert flag_allows(flag(rollout_percent=0, allowed_tenants=[str(tenant_id)]), tenant_id)


def test_a_deny_list_beats_everything():
    tenant_id = uuid7()
    assert not flag_allows(
        flag(
            rollout_percent=100, allowed_tenants=[str(tenant_id)], denied_tenants=[str(tenant_id)]
        ),
        tenant_id,
    )


@pytest.mark.parametrize(
    ("starts_in", "ends_in", "expected"),
    [
        (timedelta(hours=1), None, False),  # not started
        (timedelta(hours=-1), None, True),
        (None, timedelta(hours=-1), False),  # already finished
        (None, timedelta(hours=1), True),
    ],
)
def test_the_scheduled_window_is_respected(starts_in, ends_in, expected):
    now = timezone.now()
    scheduled = flag(
        rollout_percent=100,
        starts_at=now + starts_in if starts_in else None,
        ends_at=now + ends_in if ends_in else None,
    )
    assert flag_allows(scheduled, uuid7()) is expected


def test_buckets_stay_in_range():
    for _ in range(100):
        assert 0 <= bucket_for(CODE, uuid7()) < BUCKETS
