"""Test fixtures shared by the whole backend suite."""

from collections.abc import Iterator

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Sign-in lockout and API throttling are cache-backed.

    Without this, counters accumulated by one test would lock out or throttle the next one, and
    test order would decide whether the suite passed.
    """
    cache.clear()
    yield
    cache.clear()
