from collections.abc import Iterator

import pytest

from kernel.entitlements import manifest


@pytest.fixture
def temporary_manifests() -> Iterator[None]:
    """Let a test register modules without leaking them into every other test."""
    saved = dict(manifest._registry)
    try:
        yield
    finally:
        manifest._registry.clear()
        manifest._registry.update(saved)
