"""Operational control over features: kill switches and staged rollouts."""

import hashlib
from uuid import UUID

from django.utils import timezone

from .models import FeatureFlag

BUCKETS = 100


def bucket_for(feature_code: str, tenant_id: UUID | str) -> int:
    """Which rollout bucket an account falls in, from 0 to 99.

    Hashed from the feature code and the account id, so the same accounts stay in the same bucket
    across restarts and as the percentage is raised. Random assignment would reshuffle who has the
    feature on every deploy, which is how a rollout turns into an outage.
    """
    digest = hashlib.sha256(f"{feature_code}:{tenant_id}".encode()).hexdigest()
    return int(digest[:8], 16) % BUCKETS


def flag_allows(flag: FeatureFlag, tenant_id: UUID | str) -> bool:
    """Whether this flag lets the feature through for one account."""
    tenant_key = str(tenant_id)

    if str(tenant_key) in {str(item) for item in flag.denied_tenants}:
        return False
    if flag.is_killed:
        return False

    now = timezone.now()
    if flag.starts_at and now < flag.starts_at:
        return False
    if flag.ends_at and now > flag.ends_at:
        return False

    # An explicit allow-list beats the percentage, so a pilot pharmacy keeps the feature even at 0%.
    if tenant_key in {str(item) for item in flag.allowed_tenants}:
        return True

    if flag.rollout_percent >= BUCKETS:
        return True
    if flag.rollout_percent <= 0:
        return False
    return bucket_for(flag.feature_code, tenant_key) < flag.rollout_percent


def flags_by_code() -> dict[str, FeatureFlag]:
    return {flag.feature_code: flag for flag in FeatureFlag.objects.all()}
